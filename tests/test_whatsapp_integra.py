"""Testes offline do aviso de WhatsApp (sem rede: o envio e simulado).

  & ".\\.venv\\Scripts\\python.exe" -m unittest tests.test_whatsapp_integra -v
"""
from pathlib import Path
import json
import os
import sys
import tempfile
import unittest
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
FIXTURE = Path(__file__).with_name("fixtures") / "publicacoes_integra_anonimizado.html"

ENV = {"WA_INTEGRA_ENABLED": "true", "WA_TOKEN": "token-de-teste", "WA_PHONE_NUMBER_ID": "123456",
       "WA_API_VERSION": "v21.0", "WA_TEMPLATE_PUBLICACOES": "aviso_publicacoes", "WA_LANGUAGE": "pt_BR",
       "WA_PANEL_URL": "", "WA_INCLUIR_PARTES": "false"}


class Base(unittest.TestCase):
    def setUp(self):
        from core.store import Store
        from integrations.integra_parser import parse_listagem
        from integrations.integra_publicacoes import gravar
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        d = Path(self.tmp.name)
        self.store = Store(d / "op.sqlite")
        self.store.set_pause(False, "teste")
        with self.store.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, active INTEGER)")
            db.execute("INSERT INTO users VALUES('danilo',1)")
        rec = d / "rec.json"
        rec.write_text(json.dumps([{"username": "danilo", "phone": "5541999990000",
                                    "internal": True, "consent": True}]), encoding="utf-8")
        self.old = {k: os.environ.get(k) for k in list(ENV) + ["WA_RECIPIENTS_FILE"]}
        os.environ.update(ENV)
        os.environ["WA_RECIPIENTS_FILE"] = str(rec)
        self.novos = []
        self.resumo = gravar(self.store, parse_listagem(FIXTURE.read_text(encoding="utf-8")), novos_out=self.novos)
        self.enviados = []

    def tearDown(self):
        for k, v in self.old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.tmp.cleanup()

    def fake_send(self, c, phone, p1, p2, p3):
        self.enviados.append((phone, p1, p2, p3))
        return "wamid.TESTE"


class MensagemTests(Base):
    def test_conteudo_com_processo_vara_e_contagens(self):
        from integrations.whatsapp_integra import enfileirar
        enfileirar(self.store, self.novos, self.resumo)
        with self.store.db() as db:
            p1, p2, p3 = db.execute("SELECT p1,p2,p3 FROM whatsapp_integra_outbox").fetchone()
        self.assertIn("6 publicacao(oes) nova(s)", p1)
        self.assertIn("2 sem processo vinculado", p1)
        self.assertIn("0000003-00.2025.8.16.0003, 0000004-00.2025.8.16.0003", p2)  # 2 processos na mesma
        self.assertIn("2ª Vara Cível - Cidade C", p2)
        self.assertIn("SEM PROCESSO VINCULADO", p2)
        self.assertNotIn("Fulano", p2)                 # partes so com WA_INCLUIR_PARTES=true
        self.assertEqual(p3, "painel interno do escritorio")
        for p in (p1, p2, p3):                         # regras da Meta para parametros
            self.assertNotIn("\n", p)
            self.assertLessEqual(len(p), 900)

    def test_partes_quando_autorizado(self):
        os.environ["WA_INCLUIR_PARTES"] = "true"
        from integrations.whatsapp_integra import enfileirar
        enfileirar(self.store, self.novos, self.resumo)
        with self.store.db() as db:
            p2 = db.execute("SELECT p2 FROM whatsapp_integra_outbox").fetchone()[0]
        self.assertIn("Empresa Exemplo Alfa Ltda. x Fulano de Tal", p2)

    def test_lista_grande_e_cortada(self):
        from integrations.whatsapp_integra import montar_mensagem
        pubs = [{"processos": [{"numero_cnj": f"00000{i:02d}-00.2025.8.16.0001"}],
                 "orgao_comarca": "Vara Cível - Comarca Exemplo", "data_disponibilizacao": "08/10/2026"}
                for i in range(40)]
        _, p2, _ = montar_mensagem(pubs, {}, "")
        self.assertLessEqual(len(p2), 900)
        self.assertIn("no painel", p2)


class EnvioTests(Base):
    def test_envio_unico_por_lote(self):
        from integrations.whatsapp_integra import enfileirar, enviar_pendentes
        enfileirar(self.store, self.novos, self.resumo)
        r1 = enviar_pendentes(self.store, send=self.fake_send)
        enfileirar(self.store, self.novos, self.resumo)      # mesmo lote de novo
        r2 = enviar_pendentes(self.store, send=self.fake_send)
        self.assertEqual(r1["aceito_api"], 1)
        self.assertEqual(r2["aceito_api"], 0)
        self.assertEqual(len(self.enviados), 1)
        self.assertEqual(self.enviados[0][0], "5541999990000")
        self.assertTrue(self.store.verify())

    def test_sem_novidades_nao_envia(self):
        from integrations.whatsapp_integra import avisar
        r = avisar(self.store, [], self.resumo)
        self.assertEqual(r["lote"], "sem novidades")

    def test_pausa_bloqueia(self):
        from integrations.whatsapp_integra import enfileirar, enviar_pendentes
        self.store.set_pause(True, "teste")
        enfileirar(self.store, self.novos, self.resumo)
        r = enviar_pendentes(self.store, send=self.fake_send)
        self.assertIn("BLOQUEADO", r["motivo"])
        self.assertEqual(self.enviados, [])

    def test_desligado_por_padrao(self):
        os.environ["WA_INTEGRA_ENABLED"] = ""
        from integrations.whatsapp_integra import avisar
        self.assertIn("desligado", avisar(self.store, self.novos, self.resumo)["motivo"])

    def test_timeout_vira_reconciliar_sem_reenvio(self):
        from integrations.whatsapp_integra import enfileirar, enviar_pendentes
        def falha(*a):
            raise TimeoutError()
        enfileirar(self.store, self.novos, self.resumo)
        r = enviar_pendentes(self.store, send=falha)
        r2 = enviar_pendentes(self.store, send=self.fake_send)
        self.assertEqual(r["reconciliar"], 1)
        self.assertEqual(self.enviados, [])            # nao reenviou sozinho
        self.assertEqual(r2["aceito_api"], 0)

    def test_erro_4xx_recusado(self):
        from integrations.whatsapp_integra import enfileirar, enviar_pendentes
        def recusa(*a):
            raise urllib.error.HTTPError("u", 400, "bad", {}, None)
        enfileirar(self.store, self.novos, self.resumo)
        self.assertEqual(enviar_pendentes(self.store, send=recusa)["recusado"], 1)

    def test_numero_nao_cadastrado_nao_recebe(self):
        from integrations.whatsapp_integra import enfileirar, enviar_pendentes
        with self.store.db() as db:
            db.execute("UPDATE users SET active=0")          # usuario desativado
        self.assertIsNotNone(enfileirar(self.store, self.novos, self.resumo))
        enviar_pendentes(self.store, send=self.fake_send)
        self.assertEqual(self.enviados, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
