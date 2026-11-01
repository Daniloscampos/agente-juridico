"""Testes offline da integracao INTEGRA (sem rede, sem Chrome, sem credenciais).

Executar na pasta do projeto:
  & ".\\.venv\\Scripts\\python.exe" -m unittest tests.test_integra_integracao -v
"""
from pathlib import Path
import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIXTURE = Path(__file__).with_name("fixtures") / "publicacoes_integra_anonimizado.html"


class ParserTests(unittest.TestCase):
    def setUp(self):
        from integrations.integra_parser import parse_listagem
        self.res = parse_listagem(FIXTURE.read_text(encoding="utf-8"))

    def test_seis_publicacoes_e_rodape(self):
        self.assertEqual(len(self.res.publicacoes), 6)
        self.assertEqual((self.res.exibindo, self.res.total), (6, 6))
        self.assertTrue(self.res.completo)

    def test_duas_sem_processo_ficam_pendentes(self):
        pend = [p.codigo for p in self.res.publicacoes if p.status_vinculo == "vinculo_pendente"]
        self.assertEqual(pend, ["100000001", "100000004"])

    def test_publicacao_com_dois_processos_preserva_ambos(self):
        multi = [p for p in self.res.publicacoes if len(p.processos) > 1]
        self.assertEqual(len(multi), 1)
        self.assertEqual([x.numero_cnj for x in multi[0].processos],
                         ["0000003-00.2025.8.16.0003", "0000004-00.2025.8.16.0003"])
        self.assertEqual(multi[0].processos[1].parte_adversa, "Parte Adversa Dois")

    def test_campos_da_linha(self):
        p = self.res.publicacoes[1]
        self.assertEqual(p.codigo, "100000002")
        self.assertEqual(p.data_disponibilizacao, "08/10/2026")
        self.assertEqual(p.data_inclusao, "08/10/2026")
        self.assertEqual(p.hora_inclusao, "07:34:45")
        self.assertEqual(p.justica, "Justiça Estadual")
        self.assertEqual(p.orgao, "1ª Vara Cível")
        self.assertEqual(p.orgao_comarca, "1ª Vara Cível - Cidade A")
        self.assertEqual(p.processos[0].codigo_processo_integra, "5001")

    def test_nome_truncado_usa_title_completo(self):
        p = self.res.publicacoes[5]
        self.assertEqual(p.processos[0].parte_adversa, "Companhia Aerea Ficticia Do Continente")

    def test_layout_inesperado_bloqueia(self):
        from integrations.integra_parser import EstruturaInesperada, parse_listagem
        with self.assertRaises(EstruturaInesperada):
            parse_listagem("<div>Algo deu errado com o seu acesso. Faça o login novamente.</div>")
        with self.assertRaises(EstruturaInesperada):
            parse_listagem("<table><tbody><tr><td>1</td></tr></tbody></table>")

    def test_listagem_vazia_explicita(self):
        from integrations.integra_parser import parse_listagem
        r = parse_listagem("<span>Exibindo 0 de 0</span>")
        self.assertEqual(len(r.publicacoes), 0)
        self.assertTrue(r.completo)

    def test_rodape_divergente_nao_e_completo(self):
        from integrations.integra_parser import parse_listagem
        html = FIXTURE.read_text(encoding="utf-8").replace("Exibindo 6 de 6", "Exibindo 6 de 21")
        self.assertFalse(parse_listagem(html).completo)


class PersistenciaTests(unittest.TestCase):
    def setUp(self):
        from core.store import Store
        from integrations.integra_parser import parse_listagem
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.store = Store(Path(self.tmp.name) / "op.sqlite")
        self.res = parse_listagem(FIXTURE.read_text(encoding="utf-8"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_gravacao_idempotente(self):
        from integrations.integra_publicacoes import gravar
        r1 = gravar(self.store, self.res)
        r2 = gravar(self.store, self.res)
        self.assertEqual((r1["novas"], r1["vinculo_pendente"], r1["multiplos_processos"]), (6, 2, 1))
        self.assertEqual((r2["novas"], r2["sem_alteracao"]), (0, 6))
        with self.store.db() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM integra_publicacoes").fetchone()[0], 6)
        self.assertTrue(self.store.verify())

    def test_vinculo_posterior_atualiza(self):
        from integrations.integra_parser import Processo
        from integrations.integra_publicacoes import gravar
        gravar(self.store, self.res)
        self.res.publicacoes[0].processos.append(Processo(numero_cnj="0000009-00.2025.8.16.0009"))
        r = gravar(self.store, self.res)
        self.assertEqual(r["atualizadas"], 1)
        with self.store.db() as c:
            st = c.execute("SELECT status_vinculo FROM integra_publicacoes WHERE codigo='100000001'").fetchone()[0]
        self.assertEqual(st, "vinculada")

    def test_auditoria_sem_nomes_de_partes(self):
        from integrations.integra_publicacoes import gravar
        gravar(self.store, self.res)
        with self.store.db() as c:
            payload = c.execute("SELECT payload FROM audit ORDER BY seq DESC LIMIT 1").fetchone()[0]
        self.assertNotIn("Fulano", payload)
        self.assertEqual(json.loads(payload)["action"], "integra_publicacoes")


class SegurancaTests(unittest.TestCase):
    def test_escritas_no_integra_bloqueadas(self):
        from core.policy import Blocked
        from integrations.integra import IntegraClient
        c = IntegraClient(driver=object())
        for chamada in (lambda: c.registrar_retorno("1", "CONCLUIDO", "x"), lambda: c.concluir_tarefa("1"),
                        lambda: c.visualizar_publicacao("1"), lambda: c.listar_tarefas()):
            with self.assertRaises(Blocked):
                chamada()

    def test_codigo_nao_chama_clickVisualizar(self):
        fonte = (ROOT / "integrations" / "integra.py").read_text(encoding="utf-8")
        chamadas = [ln for ln in fonte.splitlines() if "clickVisualizar(" in ln and "execute_script" in ln]
        self.assertEqual(chamadas, [])

    def test_pausas_respeitadas(self):
        from core.policy import Blocked
        from core.store import Store
        import executar_integra as ex
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            store = Store(Path(d) / "op.sqlite")      # painel nasce PAUSADO
            with self.assertRaises(Blocked):
                ex.verificar_pausas(store)
            store.set_pause(False, "teste")
            ex.verificar_pausas(store)               # liberado
            pause_file = Path(".paused")
            criado = not pause_file.exists()
            pause_file.touch()
            try:
                with self.assertRaises(Blocked):
                    ex.verificar_pausas(store)
            finally:
                if criado:
                    pause_file.unlink()

    def test_runner_offline(self):
        import executar_integra as ex
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            os.environ["AGENT_DB"] = str(Path(d) / "op.sqlite")
            from importlib import reload
            import core.config
            reload(core.config)
            reload(ex)
            self.assertEqual(ex.main(["--html", str(FIXTURE)]), 0)
            c = sqlite3.connect(os.environ["AGENT_DB"])
            try:  # no Windows a conexao precisa ser fechada antes de apagar a pasta temporaria
                self.assertEqual(c.execute("SELECT COUNT(*) FROM integra_publicacoes").fetchone()[0], 6)
            finally:
                c.close()
            os.environ.pop("AGENT_DB")


if __name__ == "__main__":
    unittest.main(verbosity=2)
