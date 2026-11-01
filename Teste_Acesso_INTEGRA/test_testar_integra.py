import unittest
from unittest.mock import Mock
from testar_integra import evidencias_acesso, origem_permitida, exigir_agente_ativo

class TestAcesso(unittest.TestCase):
    def test_area_interna_com_menus(self):
        self.assertTrue(evidencias_acesso('https://www.integra.adv.br/moderno/modulo/132/default.asp', 'Clientes Processos Agenda', False))

    def test_formulario_nao_confirma_acesso(self):
        self.assertFalse(evidencias_acesso('https://www.integra.adv.br/moderno/teste', 'Clientes Processos Agenda', True))

    def test_menus_sozinhos_nao_confirmam(self):
        self.assertFalse(evidencias_acesso('https://www.integra.adv.br/login-integra.asp', 'Clientes Processos Agenda', False))

    def test_menus_incompletos(self):
        self.assertFalse(evidencias_acesso('https://www.integra.adv.br/moderno/teste', 'Clientes Processos', False))

    def test_origens_invalidas(self):
        for url in ['http://www.integra.adv.br/moderno/', 'https://www.integra.adv.br.evil.com/', 'https://usuario@www.integra.adv.br/', 'https://www.integra.adv.br:444/', 'https://www.integra.adv.br:invalid/']:
            with self.subTest(url=url):
                self.assertFalse(origem_permitida(url))

    def test_pausa_interrompe(self):
        control = Mock()
        control.is_paused.return_value = True
        with self.assertRaises(RuntimeError):
            exigir_agente_ativo(control)
        control.is_paused.return_value = False
        exigir_agente_ativo(control)

if __name__ == '__main__':
    unittest.main()
