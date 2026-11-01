"""Testes offline do Groq/Ollama (API compativel com OpenAI simulada) e da persona.

  .\\.venv\\Scripts\\python.exe -m unittest tests.test_ia_openai -v
"""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
C = {"PROVEDOR": "groq", "URL": "https://x", "CHAVE": "gsk_" + "a" * 30, "MODELO": "m", "VISAO": False}


class OpenAICompativelTests(unittest.TestCase):
    def test_ciclo_de_ferramenta(self):
        from integrations import ia_openai
        pedidos = []

        def post(payload, c):
            pedidos.append(json.loads(json.dumps(payload)))
            if len(pedidos) == 1:
                return {"choices": [{"message": {"content": None, "tool_calls": [
                    {"id": "c1", "type": "function",
                     "function": {"name": "publicacoes_hoje", "arguments": "{}"}}]}}]}
            return {"choices": [{"message": {"content": "Hoje há 6 publicações."}}]}

        r = ia_openai.responder("o que saiu hoje?", {"publicacoes_hoje": lambda: {"total": 6}}, c=C, post=post,
                                pessoa="Danilo", cumprimentar=True)
        self.assertEqual(r, "Hoje há 6 publicações.")
        self.assertEqual(pedidos[0]["messages"][0]["role"], "system")
        self.assertIn("Assistente Jurídico Virtual", pedidos[0]["messages"][0]["content"])
        self.assertEqual({t["function"]["name"] for t in pedidos[0]["tools"]} >= {"publicacoes_hoje",
                         "consulta_publica_processo", "agenda_prazos"}, True)
        tool_msg = pedidos[1]["messages"][-1]
        self.assertEqual((tool_msg["role"], tool_msg["tool_call_id"]), ("tool", "c1"))
        self.assertIn('"total": 6', tool_msg["content"])

    def test_erro_de_ferramenta_nao_vira_zero(self):
        from integrations import ia_openai
        pedidos = []

        def post(payload, c):
            pedidos.append(payload)
            if len(pedidos) == 1:
                return {"choices": [{"message": {"tool_calls": [
                    {"id": "c9", "function": {"name": "publicacoes_hoje", "arguments": ""}}]}}]}
            return {"choices": [{"message": {"content": "Não consegui consultar."}}]}

        def quebra():
            raise RuntimeError("fora")

        ia_openai.responder("hoje?", {"publicacoes_hoje": quebra}, c=C, post=post)
        self.assertIn("Não significa", pedidos[1]["messages"][-1]["content"])

    def test_imagem_sem_visao_e_pdf_com_texto(self):
        from integrations import ia_openai
        with self.assertRaises(ia_openai.IAErro) as cm:
            ia_openai.responder("veja", {}, imagem=("QUJD", "image/jpeg"), c=C, post=lambda p, c: {})
        self.assertIn("SEM_VISAO", str(cm.exception))
        try:
            import pypdf  # noqa: F401
        except Exception:
            self.skipTest("pypdf ausente")
        import base64
        import io
        from pypdf import PdfWriter
        w = PdfWriter()
        w.add_blank_page(width=200, height=200)
        buf = io.BytesIO()
        w.write(buf)
        with self.assertRaises(ia_openai.IAErro) as cm2:        # pagina em branco = escaneado/sem texto
            ia_openai.texto_do_pdf(base64.b64encode(buf.getvalue()).decode())
        self.assertIn("PDF_SEM_TEXTO", str(cm2.exception))

    def test_imagem_com_visao_vai_como_data_url(self):
        from integrations import ia_openai
        vistos = []
        ia_openai.responder("veja", {}, imagem=("QUJD", "image/png"), c={**C, "VISAO": True},
                            post=lambda p, c: vistos.append(p) or {"choices": [{"message": {"content": "ok"}}]})
        parte = vistos[0]["messages"][-1]["content"][1]
        self.assertEqual(parte["image_url"]["url"], "data:image/png;base64,QUJD")

    def test_config_e_validacao(self):
        import os
        from unittest import mock
        from integrations import ia_openai
        with mock.patch.dict(os.environ, {"OLLAMA_URL": "", "OLLAMA_MODELO": ""}):
            c = ia_openai.config("ollama")
        self.assertEqual((c["URL"], c["MODELO"]), ("http://127.0.0.1:11434/v1", "qwen2.5:7b"))
        self.assertEqual(ia_openai.problemas(c), [])
        self.assertTrue(ia_openai.problemas({**C, "CHAVE": ""}))


class PersonaTests(unittest.TestCase):
    def test_persona_tem_regras_do_escritorio_e_do_robo(self):
        from integrations.ia_persona import montar_system
        s = montar_system("Dr. Danilo", True)
        for trecho in ("Você NÃO é um advogado", "Nunca dê conselhos jurídicos",
                       "confirme todos os prazos e informações no processo original",
                       "Precisa de mais alguma coisa?", "Somente leitura", "Dr. Danilo",
                       "Calendário de referência", "cumprimente conforme o horário"):
            self.assertIn(trecho, s)


if __name__ == "__main__":
    unittest.main(verbosity=2)
