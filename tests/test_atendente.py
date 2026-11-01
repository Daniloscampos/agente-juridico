"""Testes offline do atendente de WhatsApp (UazAPI simulada, INTEGRA simulado).

  & ".\\.venv\\Scripts\\python.exe" -m unittest tests.test_atendente -v
"""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = Path(__file__).with_name("fixtures") / "publicacoes_integra_anonimizado.html"
NUM = "5541999990000"


class AtendenteTests(unittest.TestCase):
    def setUp(self):
        from core.store import Store
        from integrations.atendente import Atendente
        from integrations.integra_parser import parse_listagem
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(Path(self.tmp.name) / "op.sqlite")
        self.store.set_pause(False, "teste")
        self.enviados, self.consultas, self.falhar = [], 0, False
        html = FIXTURE.read_text(encoding="utf-8")

        def consultar():
            self.consultas += 1
            if self.falhar:
                raise RuntimeError("INTEGRA fora")
            return parse_listagem(html)

        self.at = Atendente(self.store, {NUM: "danilo"}, consultar, lambda n, t: self.enviados.append((n, t)) or "id")
        self.seq = 0

    def tearDown(self):
        self.tmp.cleanup()

    def msg(self, texto, numero=NUM, **kw):
        self.seq += 1
        return {"id": f"m{self.seq}", "numero": numero, "texto": texto, "de_mim": False,
                "grupo": False, "pela_api": False, **kw}

    def test_interpretacao(self):
        from integrations.atendente import interpretar
        self.assertEqual(interpretar("Publicações hoje")[0], "hoje")
        self.assertEqual(interpretar("hoje")[0], "hoje")
        self.assertEqual(interpretar("publicacoes 07/10/2026"), ("data", "07/10/2026"))
        self.assertEqual(interpretar("processo 0000003-00.2025.8.16.0003"), ("processo", "00000030020258160003"))
        self.assertEqual(interpretar("sem vínculo")[0], "sem_vinculo")
        self.assertEqual(interpretar("protocola a petição do processo 0000003-00.2025.8.16.0003")[0], "proibido")
        self.assertEqual(interpretar("marque como lida")[0], "proibido")
        self.assertEqual(interpretar("bom dia")[0], "ajuda")
        self.assertEqual(interpretar("qual o placar do jogo")[0], "desconhecido")

    def test_publicacoes_hoje_ao_vivo(self):
        r = self.at.processar(self.msg("publicações hoje"))
        self.assertIn("hoje há 6 publicações, sendo 2 ainda sem processo vinculado", r)
        self.assertIn("0000003-00.2025.8.16.0003, 0000004-00.2025.8.16.0003", r)
        self.assertIn("20ª Câmara de Direito Cível - Curitiba", r)
        self.assertEqual(self.enviados[0][0], NUM)
        self.assertLessEqual(len(r), 3500)

    def test_processo_e_sem_vinculo(self):
        r = self.at.processar(self.msg("processo 0000001-00.2025.8.16.0001"))
        self.assertIn("encontrei 1 publicação", r)
        self.assertIn("1ª Vara Cível - Cidade A", r)
        r2 = self.at.processar(self.msg("sem vinculo"))
        self.assertIn("há 2 publicações, todas ainda sem processo vinculado", r2)
        self.assertEqual(self.consultas, 1)   # cache evita reconsultar o INTEGRA em seguida

    def test_falha_do_integra_nunca_vira_zero(self):
        self.falhar = True
        r = self.at.processar(self.msg("hoje"))
        self.assertIn("não consegui acessar o INTEGRA", r)
        self.assertIn("não quer dizer que não haja publicações", r)

    def test_numero_nao_autorizado_e_grupo_ignorados(self):
        self.assertIsNone(self.at.processar(self.msg("hoje", numero="5511888887777")))
        self.assertIsNone(self.at.processar(self.msg("hoje", grupo=True)))
        self.assertIsNone(self.at.processar(self.msg("hoje", de_mim=True)))
        self.assertEqual(self.enviados, [])

    def test_mesma_mensagem_uma_resposta(self):
        m = self.msg("hoje")
        self.at.processar(m)
        self.assertIsNone(self.at.processar(m))
        self.assertEqual(len(self.enviados), 1)

    def test_pausa_nao_consulta_nem_responde(self):
        self.store.set_pause(True, "teste")
        self.assertIsNone(self.at.processar(self.msg("hoje")))
        self.assertEqual((self.enviados, self.consultas), ([], 0))

    def test_pedido_proibido_recusado_sem_consultar(self):
        r = self.at.processar(self.msg("pode protocolar a manifestação?"))
        self.assertIn("sem protocolar, assinar", r)
        self.assertEqual(self.consultas, 0)

    def test_ja_visto_evita_repeticao(self):
        m = self.msg("hoje")
        self.assertFalse(self.at.ja_visto(m["id"]))
        self.at.processar(m)
        self.assertTrue(self.at.ja_visto(m["id"]))
        self.assertFalse(self.at.ja_visto(""))

    def test_auditoria_sem_conteudo(self):
        self.at.processar(self.msg("processo 0000001-00.2025.8.16.0001"))
        with self.store.db() as db:
            payloads = [r[0] for r in db.execute("SELECT payload FROM audit")]
        self.assertTrue(any('"atendimento_whatsapp"' in p for p in payloads))
        self.assertFalse(any("0000001-00.2025" in p for p in payloads))
        self.assertTrue(self.store.verify())


class UazapiTests(unittest.TestCase):
    def test_extrair_mensagem(self):
        from integrations.uazapi import extrair_mensagem
        ev = {"EventType": "messages", "message": {"chatid": "5541999990000@s.whatsapp.net",
              "sender": "5541999990000@s.whatsapp.net", "text": "hoje", "fromMe": False,
              "isGroup": False, "messageid": "ABC"}}
        m = extrair_mensagem(ev)
        self.assertEqual((m["numero"], m["texto"], m["id"], m["de_mim"]), (NUM, "hoje", "ABC", False))
        grupo = {"EventType": "messages", "message": {"chatid": "123@g.us", "text": "x", "messageid": "G"}}
        self.assertTrue(extrair_mensagem(grupo)["grupo"])
        self.assertIsNone(extrair_mensagem({"EventType": "connection"}))

    def test_sse_le_eventos(self):
        import io
        from integrations import uazapi
        bruto = (b'data: {"EventType":"messages","message":{"chatid":"5541999990000@s.whatsapp.net",'
                 b'"text":"hoje","messageid":"X1"}}\n\n: ping\n\n')
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        original = uazapi._abrir
        uazapi._abrir = lambda req, timeout: Resp(bruto)
        try:
            gen = uazapi.eventos({"URL": "https://x.uazapi.com", "TOKEN": "t" * 12})
            ev = next(gen)
        finally:
            uazapi._abrir = original
        self.assertEqual(uazapi.extrair_mensagem(ev)["id"], "X1")

    def test_busca_de_reserva(self):
        import io, json as _j
        from integrations import uazapi
        corpo = _j.dumps({"messages": [
            {"messageid": "B1", "chatid": "5541999990000@s.whatsapp.net", "sender": "5541999990000@s.whatsapp.net",
             "text": "publicacoes hoje", "fromMe": False, "messageTimestamp": 1791500000000},
            {"messageid": "B2", "chatid": "5541999990000@s.whatsapp.net", "text": "resposta do robo",
             "fromMe": True, "messageTimestamp": 1791500001}]}).encode()
        class Resp(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        original = uazapi._abrir
        uazapi._abrir = lambda req, timeout: Resp(corpo)
        try:
            ms = uazapi.buscar_mensagens(NUM, c={"URL": "https://x.uazapi.com", "TOKEN": "t" * 12})
        finally:
            uazapi._abrir = original
        self.assertEqual([(m["id"], m["de_mim"]) for m in ms], [("B1", False), ("B2", True)])
        self.assertAlmostEqual(ms[0]["ts"], 1791500000.0)
        self.assertAlmostEqual(ms[1]["ts"], 1791500001.0)

    def test_texto_livre_do_aviso(self):
        from integrations.whatsapp_integra import texto_livre
        t = texto_livre("2 novas", "1) A - Vara | 2) B - Vara", "painel")
        self.assertIn("Processos:\n1) A - Vara\n2) B - Vara", t)
        self.assertIn("responda: ajuda", t)

    def test_config(self):
        from integrations.uazapi import problemas
        self.assertTrue(problemas({"URL": "http://x.com", "TOKEN": ""}))
        self.assertEqual(problemas({"URL": "https://escritorio.uazapi.com", "TOKEN": "abcdefghijkl"}), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
