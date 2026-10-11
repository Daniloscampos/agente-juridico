import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from integra.agenda_integra import (
    AgendaIntegra, AgendaErro, AgendaSessaoExpirada,
    AgendaParserNaoHomologado, interpretar_fragmento, salvar_amostra_mascarada,
)

VAZIO = '''<div id="divPesquisaAgendaListar"><span class="total">Resultados encontrados: exibindo 0 de 0</span><div class="even empty">Você não possui agendamento nesse período</div></div>'''
LOGIN = '<html><body><form id="login"><input type="password" name="senha" /></form></body></html>'
COM_REGISTROS = '<div><span class="total">Resultados encontrados: exibindo 2 de 2</span><div class="item">Cliente confidencial 123456</div></div>'

class TestAgenda(unittest.TestCase):
    def test_vazio_confirmado(self):
        self.assertEqual(interpretar_fragmento(VAZIO), [])

    def test_sessao_expirada(self):
        with self.assertRaises(AgendaSessaoExpirada):
            interpretar_fragmento(LOGIN)

    def test_resposta_curta(self):
        with self.assertRaises(AgendaErro):
            interpretar_fragmento('erro')

    def test_nao_inventar_linhas(self):
        with self.assertRaises(AgendaParserNaoHomologado):
            interpretar_fragmento(COM_REGISTROS)

    def test_interface_e_consulta_mockada(self):
        with patch('integra.agenda_integra._consultar_fragmento', return_value=VAZIO) as mock:
            self.assertEqual(AgendaIntegra(object()).listar_tarefas('2026-10-05', '2026-10-11'), [])
            self.assertEqual(mock.call_count, 1)

    def test_amostra_nao_expoe_texto(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = salvar_amostra_mascarada(COM_REGISTROS, Path(pasta) / 'amostra.txt')
            saida = caminho.read_text(encoding='utf-8')
            self.assertNotIn('Cliente confidencial', saida)
            self.assertNotIn('123456', saida)

if __name__ == '__main__':
    unittest.main()
