"""Testes offline da IA (Claude simulado), audio/imagem e voz. Sem rede, sem chave, sem Whisper.

  & ".\\.venv\\Scripts\\python.exe" -m unittest tests.test_ia_voz -v
"""
from pathlib import Path
import base64
import io
import json
import sys
import tempfile
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = Path(__file__).with_name("fixtures") / "publicacoes_integra_anonimizado.html"
NUM = "5541999990000"
C = {"CHAVE": "k" * 30, "MODELO": "modelo-teste", "MAX_TOKENS": 100, "ATIVA": True}


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class ClaudeTests(unittest.TestCase):
    def test_ferramenta_e_resposta_final(self):
        from integrations import ia_claude
        enviados = []

        def post(payload, c):
            enviados.append(json.loads(json.dumps(payload)))
            if len(enviados) == 1:
                return {"stop_reason": "tool_use", "content": [
                    {"type": "text", "text": "vou consultar"},
                    {"type": "tool_use", "id": "t1", "name": "publicacoes_hoje", "input": {}}]}
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Hoje: 6 publicações."}]}

        r = ia_claude.responder("quantas publicações hoje?", {"publicacoes_hoje": lambda: {"total": 6}},
                                c=C, post=post)
        self.assertEqual(r, "Hoje: 6 publicações.")
        self.assertEqual(len(enviados), 2)
        self.assertEqual(enviados[0]["model"], "modelo-teste")
        self.assertIn("Somente leitura", enviados[0]["system"])
        resultado = enviados[1]["messages"][-1]["content"][0]
        self.assertEqual((resultado["type"], resultado["tool_use_id"]), ("tool_result", "t1"))
        self.assertIn('"total": 6', resultado["content"])

    def test_erro_de_ferramenta_vira_aviso_e_imagem_vai_no_pedido(self):
        from integrations import ia_claude
        chamadas = []

        def post(payload, c):
            chamadas.append(payload)
            if len(chamadas) == 1:
                return {"stop_reason": "tool_use", "content": [
                    {"type": "tool_use", "id": "t9", "name": "publicacoes_hoje", "input": {}}]}
            return {"stop_reason": "end_turn", "content": [{"type": "text", "text": "Não consegui consultar."}]}

        def quebra():
            raise RuntimeError("INTEGRA fora")

        ia_claude.responder("", {"publicacoes_hoje": quebra}, imagem=("QUJD", "image/jpeg"), c=C, post=post)
        bloco_img = chamadas[0]["messages"][0]["content"][0]
        self.assertEqual(bloco_img["source"], {"type": "base64", "media_type": "image/jpeg", "data": "QUJD"})
        res = chamadas[1]["messages"][-1]["content"][0]
        self.assertTrue(res["is_error"])
        self.assertIn("Não significa", res["content"])

    def test_sem_ferramentas_de_escrita(self):
        from integrations.ia_claude import FERRAMENTAS
        nomes = {f["name"] for f in FERRAMENTAS}
        self.assertEqual(nomes, {"publicacoes_hoje", "publicacoes_por_processo", "publicacoes_por_data",
                                 "publicacoes_sem_vinculo", "consulta_publica_processo", "agenda_prazos"})

    def test_chave_validada(self):
        from integrations.ia_claude import problemas
        self.assertTrue(problemas({"CHAVE": ""}))
        self.assertEqual(problemas({"CHAVE": "sk-ant-" + "x" * 30}), [])


class AtendenteIATests(unittest.TestCase):
    def setUp(self):
        from core.store import Store
        from integrations.atendente import Atendente
        from integrations.integra_parser import parse_listagem
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(Path(self.tmp.name) / "op.sqlite")
        self.store.set_pause(False, "teste")
        html = FIXTURE.read_text(encoding="utf-8")
        self.enviados, self.falas, self.ia_chamadas = [], [], []
        self.transcricao, self.falha_ia = "publicações de hoje", False

        def ia(texto, ferramentas, imagem, historico, **kw):
            self.ia_chamadas.append((texto, imagem, historico))
            if self.falha_ia:
                raise RuntimeError("api fora")
            dados = ferramentas["publicacoes_por_processo"]("0000003-00.2025.8.16.0003")
            return f"Achei {dados['total']} publicação(ões)."

        test = self

        class Midia:
            def transcrever(self, msg):
                if test.transcricao is None:
                    raise RuntimeError("audio ruim")
                return test.transcricao

            def imagem(self, msg):
                return ("QUJD", "image/jpeg")

        self.at = Atendente(self.store, {NUM: "danilo"}, lambda: parse_listagem(html),
                            lambda n, t: self.enviados.append(t) or "id", ia=ia, midia=Midia(),
                            falar=lambda n, t: self.falas.append(t))
        self.seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def msg(self, texto="", tipo="texto"):
        self.seq += 1
        return {"id": f"m{self.seq}", "numero": NUM, "texto": texto, "tipo": tipo,
                "de_mim": False, "grupo": False, "pela_api": False}

    def test_pedido_livre_vai_para_ia_com_ferramentas(self):
        r = self.at.processar(self.msg("me fala do processo da cidade C"))
        self.assertEqual(r, "Achei 1 publicação(ões).")
        self.assertEqual(self.falas, [])                       # texto -> resposta so em texto

    def test_proibido_nunca_chega_na_ia(self):
        r = self.at.processar(self.msg("protocola a petição pra mim"))
        self.assertIn("sem protocolar, assinar", r)
        self.assertEqual(self.ia_chamadas, [])

    def test_audio_com_pedido_conhecido_responde_direto_e_em_voz(self):
        r = self.at.processar(self.msg(tipo="audio"))
        self.assertNotIn("Entendi:", r)                        # sem eco da transcricao
        self.assertIn("hoje há 6 publicações", r)
        self.assertEqual(self.ia_chamadas, [])
        self.assertEqual(len(self.falas), 1)

    def test_audio_proibido_recusado(self):
        self.transcricao = "assina o documento"
        r = self.at.processar(self.msg(tipo="audio"))
        self.assertIn("sem protocolar, assinar", r)
        self.assertEqual(self.ia_chamadas, [])

    def test_audio_ilegivel(self):
        self.transcricao = None
        r = self.at.processar(self.msg(tipo="audio"))
        self.assertIn("Não consegui entender o áudio", r)
        self.assertEqual(self.falas, [])

    def test_imagem_vai_para_ia(self):
        r = self.at.processar(self.msg("o que é isso?", tipo="imagem"))
        self.assertEqual(r, "Achei 1 publicação(ões).")
        self.assertEqual(self.ia_chamadas[0][1], ("QUJD", "image/jpeg"))

    def test_falha_da_ia_tem_resposta_segura(self):
        self.falha_ia = True
        r = self.at.processar(self.msg("me ajuda com uma coisa diferente"))
        self.assertIn("instabilidade", r)
        for proibida in ("modo de contingência", "Recebi sua mensagem", "tente novamente", "•"):
            self.assertNotIn(proibida, r)
        r2 = self.at.processar(self.msg("me ajuda com uma coisa diferente"))
        self.assertNotEqual(r.split(". ", 1)[-1], r2)           # nunca repete o mesmo texto em sequencia

    def test_memoria_curta(self):
        self.at.processar(self.msg("me fala do processo da cidade C"))
        self.at.processar(self.msg("e o anterior?"))
        hist = self.ia_chamadas[1][2]
        self.assertEqual([m["role"] for m in hist], ["user", "assistant"])

    def test_tipo_nao_suportado(self):
        r = self.at.processar(self.msg(tipo="outro"))
        self.assertIn("Esse tipo de arquivo eu ainda não consigo abrir", r)

    def test_ferramentas_validam_entrada_e_omitem_partes(self):
        f = self.at._ferramentas()
        self.assertIn("erro", f["publicacoes_por_processo"]("123"))
        self.assertIn("erro", f["publicacoes_por_data"]("2026-10-08"))
        hoje = f["publicacoes_hoje"]()
        self.assertEqual((hoje["total"], hoje["sem_vinculo"]), (6, 2))
        self.assertNotIn("Fulano", json.dumps(hoje, ensure_ascii=False))

    def test_reacao_e_vazio_ignorados_sem_ia(self):
        self.assertIsNone(self.at.processar(self.msg("👍", tipo="ignorar")))
        self.assertIsNone(self.at.processar(self.msg("   ")))
        self.assertEqual((self.enviados, self.ia_chamadas), ([], []))

    def test_legenda_proibida_recusa_antes_de_baixar(self):
        test = self

        class SemDownload:
            def imagem(self, msg):
                test.fail("nao deveria baixar")

        self.at.midia = SemDownload()
        r = self.at.processar(self.msg("assina isso", tipo="imagem"))
        self.assertIn("sem protocolar, assinar", r)

    def test_pausa_ligada_durante_o_pedido_nao_envia(self):
        from core import control
        criado = not control.PAUSE_FILE.exists()

        def ia_lenta(texto, ferramentas, imagem, historico, **kw):
            control.PAUSE_FILE.touch()          # alguem pausa enquanto a IA pensa
            return "resposta"

        self.at.ia = ia_lenta
        try:
            self.assertIsNone(self.at.processar(self.msg("me fala do processo da cidade C")))
        finally:
            if criado and control.PAUSE_FILE.exists():
                control.PAUSE_FILE.unlink()
        self.assertEqual(self.enviados, [])

    def test_partes_com_x_no_nome(self):
        import os
        os.environ["WA_INCLUIR_PARTES"] = "true"
        try:
            d = self.at._pub_ia({"processos": [{"numero_cnj": "1", "cliente": "Max", "parte_adversa": "Felix"}]})
        finally:
            os.environ.pop("WA_INCLUIR_PARTES")
        self.assertEqual(d["partes"], ["Max x Felix"])

    def test_cumprimenta_uma_vez_e_trata_pelo_nome(self):
        self.at.nomes = {NUM: "Dr. Danilo"}
        r1 = self.at.processar(self.msg("publicacoes hoje"))
        r2 = self.at.processar(self.msg("sem vinculo"))
        self.assertRegex(r1, r"^(Bom dia|Boa tarde|Boa noite), Dr\. Danilo\. Consultei o INTEGRA")
        self.assertTrue(r2.startswith("Verifiquei os registros"))

    def test_ia_recebe_nome_e_pedido_de_cumprimento(self):
        vistos = []
        self.at.ia = lambda t, f, i, h, **kw: vistos.append(kw) or "ok"
        self.at.processar(self.msg("me fala do processo da cidade C"))
        self.at.processar(self.msg("e o outro?"))
        self.assertEqual(vistos[0], {"pessoa": "Danilo", "cumprimentar": True})
        self.assertFalse(vistos[1]["cumprimentar"])

    def test_voz_nao_le_a_transcricao(self):
        self.at.processar(self.msg(tipo="audio"))
        self.assertNotIn("Entendi", self.falas[0])
        self.assertIn("Consultei o INTEGRA", self.falas[0])

    def test_erro_tecnico_vira_explicacao_simples(self):
        from integrations.atendente import motivo_amigavel

        class InvalidSessionIdException(Exception):
            pass

        self.assertIn("janela do sistema", motivo_amigavel(InvalidSessionIdException("invalid session id")))
        self.at.consultar_hoje = lambda: (_ for _ in ()).throw(InvalidSessionIdException("x"))
        r = self.at.processar(self.msg("publicacoes hoje"))
        self.assertNotIn("Exception", r)
        self.assertIn("não quer dizer que não haja publicações", r)

    def test_ferramentas_respeitam_limites_do_painel(self):
        self.store.limit("consulta_publica", True, "admin")
        r = self.at._ferramentas()["consulta_publica_processo"](numero_cnj="0000003-00.2025.8.16.0003")
        self.assertTrue(r["bloqueado"])
        self.assertIn("intervenção humana", r["motivo"])

    def test_resumo_bloqueado_no_painel_nao_chama_ia(self):
        self.store.limit("resumo", True, "admin")
        r = self.at.processar(self.msg("me fala do processo da cidade C"))
        self.assertIn("reservado para a equipe", r)
        self.assertEqual(self.ia_chamadas, [])

    def test_documento_pdf_vai_para_ia(self):
        test = self

        class M:
            def documento(self, msg):
                return ("JVBERi0=", "application/pdf")

            def imagem(self, msg):
                test.fail("nao e imagem")

        self.at.midia = M()
        r = self.at.processar(self.msg("analise este documento", tipo="documento"))
        self.assertEqual(r, "Achei 1 publicação(ões).")
        self.assertEqual(self.ia_chamadas[0][1], ("JVBERi0=", "application/pdf"))

    def test_agenda_com_ia_vai_para_ia_sem_ia_explica(self):
        from integrations.atendente import Atendente
        self.at.processar(self.msg("quais processos temos pra terça da semana que vem"))
        self.assertEqual(len(self.ia_chamadas), 1)
        sem = Atendente(self.store, {NUM: "danilo"}, self.at.consultar_hoje, lambda n, t: "id")
        r = sem.processar(self.msg("tenho audiência amanhã?"))
        self.assertIn("agenda, os prazos ou as audiências", r)

    def test_modelo_sem_visao_explica(self):
        def ia_sem_visao(t, f, i, h, **kw):
            raise RuntimeError("SEM_VISAO")
        self.at.ia = ia_sem_visao
        r = self.at.processar(self.msg("o que é isso?", tipo="imagem"))
        self.assertIn("imagem eu não consigo ler", r)

    def test_sem_ia_continua_como_antes(self):
        from integrations.atendente import Atendente
        at = Atendente(self.store, {NUM: "danilo"}, self.at.consultar_hoje, lambda n, t: "id")
        self.assertIn("Não consegui entender bem", at.processar(self.msg("qual o placar")))
        self.assertIn("não consigo ouvir áudios", at.processar(self.msg(tipo="audio")))
        self.assertIn("não consigo ler imagens por aqui", at.processar(self.msg(tipo="imagem")))


class AssistenteJuridicoTests(unittest.TestCase):
    def test_datas_relativas(self):
        from datetime import date
        from integrations.atendente import data_relativa
        sexta = date(2026, 10, 9)                      # sexta-feira
        self.assertEqual(data_relativa("publicacoes de ontem", sexta), date(2026, 10, 8))
        self.assertEqual(data_relativa("terca da semana que vem", sexta, futuro=True), date(2026, 10, 13))
        self.assertEqual(data_relativa("segunda passada", sexta), date(2026, 10, 5))
        self.assertEqual(data_relativa("amanha", sexta), date(2026, 10, 10))
        self.assertIsNone(data_relativa("bom dia", sexta))

    def test_intencoes(self):
        from integrations.atendente import interpretar
        self.assertEqual(interpretar("quais são os processos que a gente tem pra terça-feira da semana que vem")[0],
                         "agenda")
        self.assertEqual(interpretar("tenho audiência amanhã?")[0], "agenda")
        self.assertEqual(interpretar("publicações de ontem")[0], "data")
        self.assertEqual(interpretar("analise esse documento pra mim, por favor")[0], "desconhecido")

    def test_consulta_publica(self):
        import os
        from unittest import mock
        from integrations import consulta_publica as cp
        self.assertEqual(cp.indice("00000030020258160003"), "api_publica_tjpr")
        self.assertEqual(cp.indice("00000030020255090003"), "api_publica_trt9")
        dados = {"hits": {"hits": [{"_source": {"tribunal": "TJPR", "classe": {"nome": "Procedimento Comum"},
                 "orgaoJulgador": {"nome": "2ª Vara Cível"}, "assuntos": [{"nome": "Indenização"}],
                 "movimentos": [{"dataHora": "2026-10-01T10:00:00", "nome": "Conclusão"},
                                {"dataHora": "2026-10-05T10:00:00", "nome": "Decisão"}]}}]}}
        with mock.patch.dict(os.environ, {"DATAJUD_API_KEY": "chave-publica"}):
            r = cp.consultar("0000003-00.2025.8.16.0003", post=lambda req: dados)
            vazio = cp.consultar("0000003-00.2025.8.16.0003", post=lambda req: {"hits": {"hits": []}})
        self.assertEqual((r["classe"], r["ultimas_movimentacoes"][0]["movimento"]), ("Procedimento Comum", "Decisão"))
        self.assertFalse(vazio["encontrado"])
        with mock.patch.dict(os.environ, {"DATAJUD_API_KEY": ""}):
            self.assertFalse(cp.consultar("0000003-00.2025.8.16.0003")["disponivel"])

    def test_pdf_vai_como_documento(self):
        from integrations import ia_claude
        enviados = []
        ia_claude.responder("resuma", {}, imagem=("JVBERi0=", "application/pdf"), c=C,
                            post=lambda p, c: enviados.append(p) or {"stop_reason": "end_turn",
                                                                     "content": [{"type": "text", "text": "ok"}]})
        self.assertEqual(enviados[0]["messages"][0]["content"][0]["type"], "document")
        self.assertIn("Calendário de referência", enviados[0]["system"])


class UazapiMidiaTests(unittest.TestCase):
    CFG = {"URL": "https://x.uazapi.com", "TOKEN": "t" * 12}

    def test_tipo_mensagem(self):
        from integrations.uazapi import tipo_mensagem
        self.assertEqual(tipo_mensagem({"messageType": "AudioMessage"}), "audio")
        self.assertEqual(tipo_mensagem({"messageType": "ImageMessage"}), "imagem")
        self.assertEqual(tipo_mensagem({"mediaType": "ptt"}), "audio")
        self.assertEqual(tipo_mensagem({"messageType": "DocumentMessage"}), "documento")
        self.assertEqual(tipo_mensagem({"messageType": "VideoMessage"}), "outro")
        self.assertEqual(tipo_mensagem({"messageType": "StickerMessage", "mediaType": "image"}), "outro")
        self.assertEqual(tipo_mensagem({"messageType": "ExtendedTextMessage"}), "texto")
        self.assertEqual(tipo_mensagem({"messageType": "ReactionMessage"}), "ignorar")
        self.assertEqual(tipo_mensagem({"messageType": "ProtocolMessage"}), "ignorar")

    def test_baixar_tenta_segundo_id_e_decodifica(self):
        from integrations import uazapi
        pedidos = []

        def abrir(req, timeout):
            corpo = json.loads(req.data)
            pedidos.append(corpo["id"])
            if corpo["id"] == "A":
                raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, None)
            return Resp(json.dumps({"mimetype": "audio/mpeg",
                                    "base64Data": base64.b64encode(b"MP3").decode()}).encode())

        original = uazapi._abrir
        uazapi._abrir = abrir
        try:
            dados, mime = uazapi.baixar_midia(["A", "B"], c=self.CFG)
        finally:
            uazapi._abrir = original
        self.assertEqual((dados, mime, pedidos), (b"MP3", "audio/mpeg", ["A", "B"]))

    def test_enviar_audio_ptt(self):
        from integrations import uazapi
        visto = {}

        def abrir(req, timeout):
            visto.update(json.loads(req.data))
            visto["url"] = req.full_url
            return Resp(b'{"messageid": "X"}')

        original = uazapi._abrir
        uazapi._abrir = abrir
        try:
            self.assertEqual(uazapi.enviar_audio(NUM, b"OGG", c=self.CFG), "X")
        finally:
            uazapi._abrir = original
        self.assertEqual((visto["type"], visto["number"], visto["url"]), ("ptt", NUM, "https://x.uazapi.com/send/media"))
        self.assertEqual(base64.b64decode(visto["file"]), b"OGG")


class VozTests(unittest.TestCase):
    def test_texto_para_fala(self):
        from integrations.voz import MAX_FALA, texto_para_fala
        t = texto_para_fala("*Total: 6* 😀\n• 1) processo\nhttps://x.com/a")
        self.assertNotIn("*", t)
        self.assertNotIn("http", t)
        self.assertNotIn("😀", t)
        longo = texto_para_fala("Frase de teste. " * 200)
        self.assertLessEqual(len(longo), MAX_FALA + 60)
        self.assertTrue(longo.endswith("O restante está na mensagem de texto."))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCorrecoes20261009(unittest.TestCase):
    def test_ultimo_dia_citado_vale(self):
        from datetime import date
        from integrations.atendente import data_relativa, _normal, interpretar
        t = _normal("Segunda-feira é feriado. Quero saber quais são os processos que a gente tem pra terça-feira da semana que vem")
        self.assertEqual(data_relativa(t, hoje=date(2026, 10, 9), futuro=True), date(2026, 10, 13))
        self.assertEqual(interpretar("quais processos temos pra terça-feira da semana que vem")[0], "agenda")

    def test_eleven_falha_usa_voz_do_windows(self):
        from unittest import mock
        from integrations import voz, elevenlabs
        with mock.patch.object(voz, "provedor_voz", return_value="elevenlabs"), \
             mock.patch.object(elevenlabs, "falar", side_effect=RuntimeError("HTTP 401 quota_exceeded")), \
             mock.patch.object(voz, "voz_windows", return_value="Maria"), \
             mock.patch.object(voz, "_sintetizar_windows", return_value=(b"ogg", "audio/ogg")) as w:
            self.assertEqual(voz.sintetizar("Bom dia, Danilo."), (b"ogg", "audio/ogg"))
            w.assert_called_once()


class TestHumanizado(unittest.TestCase):
    def test_textos_fixos_sem_frases_robotizadas(self):
        from integrations import atendente as a
        textos = [a.AJUDA, a.LIMITES] + [t for v in a.VARIANTES.values() for t in v]
        for t in textos:
            for ruim in ("modo de contingência", "Recebi sua mensagem", "tente novamente", "Entendi:", "•"):
                self.assertNotIn(ruim, t)
        self.assertNotIn("não protocolo", a.AJUDA)       # limites so quando pedirem algo assim


class TestClassificacaoDocumentos(unittest.TestCase):
    def test_persona_classifica_antes_de_analisar(self):
        from integrations.ia_persona import montar_system
        for modo in ("completo", "rapido", "contingencia"):
            s = montar_system(modo=modo)
            self.assertIn("Classificação de documentos", s)
            self.assertIn("não parece ser um processo judicial ou uma publicação do INTEGRA", s)
            self.assertLess(s.index("Classificação de documentos"), s.index("## Análise de documento"))
