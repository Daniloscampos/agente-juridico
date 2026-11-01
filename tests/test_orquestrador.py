"""Testes do orquestrador de IA (Claude > Groq > Ollama com troca automatica).

  .\\.venv\\Scripts\\python.exe -m unittest tests.test_orquestrador -v
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def prov(nome, resposta=None, erro=None, chamadas=None, **kw):
    from integrations.ia_orquestrador import Provedor

    def fn(texto, ferramentas, imagem, hist, **k):
        if chamadas is not None:
            chamadas.append((nome, k.get("modo")))
        if erro:
            raise RuntimeError(erro)
        return resposta or f"resposta {nome}"
    return Provedor(nome, fn, **kw)


class OrquestradorTests(unittest.TestCase):
    def orq(self, provs, rel=None):
        from integrations.ia_orquestrador import Orquestrador
        return Orquestrador(provs, relogio=rel or Relogio(), gravar_estado=False)

    def test_prioridade_e_modo(self):
        ch = []
        o = self.orq([prov("ollama", chamadas=ch), prov("claude", chamadas=ch), prov("groq", chamadas=ch)])
        self.assertEqual(o("oi", {}), "resposta claude")
        self.assertEqual(ch, [("claude", "completo")])

    def test_sem_credito_cai_para_groq_e_pausa_claude(self):
        ch = []
        rel = Relogio()
        o = self.orq([prov("claude", erro="HTTP 400: Your credit balance is too low", chamadas=ch),
                      prov("groq", chamadas=ch)], rel)
        self.assertEqual(o("oi", {}, pessoa="Danilo"), "resposta groq")
        self.assertEqual(ch, [("claude", "completo"), ("groq", "rapido")])
        ch.clear()
        o("de novo", {}, pessoa="Danilo")           # Claude em pausa: nem tenta
        self.assertEqual(ch, [("groq", "rapido")])
        rel.t += 3601                                  # depois de 1 h, tenta o Claude de novo
        o("mais uma", {}, pessoa="Danilo")
        self.assertEqual(ch[-2][0], "claude")

    def test_limite_de_uso_pausa_curta_e_ollama_assume(self):
        from integrations.ia_orquestrador import pausa_para
        self.assertEqual(pausa_para("HTTP 429 rate limit"), 120)
        o = self.orq([prov("groq", erro="HTTP 429 rate limit"), prov("ollama")])
        self.assertEqual(o("oi", {}), "resposta ollama")

    def test_troca_no_meio_da_conversa_e_invisivel(self):
        rel = Relogio()
        claude = prov("claude")
        o = self.orq([claude, prov("groq")], rel)
        self.assertEqual(o("1", {}, pessoa="Ana"), "resposta claude")
        claude.pausado_ate = rel.t + 600               # Claude cai no meio da conversa
        r = o("2", {}, pessoa="Ana")
        self.assertEqual(r, "resposta groq")            # sem frase de transicao (diretriz humanizada)
        self.assertNotIn("Claude", r.replace("resposta claude", ""))

    def test_imagem_so_vai_para_quem_le_imagem(self):
        ch = []
        o = self.orq([prov("claude", erro="HTTP 400 credit balance", chamadas=ch, le_imagem=True),
                      prov("groq", chamadas=ch, le_imagem=False)])
        with self.assertRaises(Exception) as cm:
            o("veja", {}, imagem=("QUJD", "image/jpeg"))
        self.assertEqual([c[0] for c in ch], ["claude"])
        self.assertNotIn("groq", str(cm.exception).lower())

    def test_todos_fora_levanta_erro(self):
        o = self.orq([prov("claude", erro="timeout"), prov("groq", erro="HTTP 503")])
        with self.assertRaises(Exception):
            o("oi", {})
        estado = o.estado()["provedores"]
        self.assertTrue(all(not p["disponivel"] for p in estado))

    def test_persona_modo_contingencia(self):
        from integrations.ia_persona import montar_system
        s = montar_system(modo="contingencia")
        from integrations.ia_persona import MODOS
        self.assertIn("contexto curto", s)
        self.assertNotIn("modo de contingência", MODOS["contingencia"])
        self.assertIn('Nunca comece com "Entendi', s)
        self.assertIn("Nunca mencione nomes de modelos", s)
        self.assertNotIn("Modo de operação", montar_system(modo="completo"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
