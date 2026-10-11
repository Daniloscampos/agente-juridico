import unittest
from orquestrador.orquestrador_tarefas import (preparar_fila, gerar_preview, TarefaInvalida, FonteNaoHomologada)

EXEMPLO = dict(data_hora='2026-10-12 09:00', tipo='GUIA', status='NAOCONCLUIDO',
               cliente='PESSOA_PRIVADA', processo='NUMERO_PRIVADO', descricao='DETALHE_PRIVADO')

class TestEtapa65(unittest.TestCase):
    def test_vazio(self):
        self.assertEqual(gerar_preview([])['total'], 0)
    def test_deduplicacao(self):
        self.assertEqual(len(preparar_fila([EXEMPLO, EXEMPLO])), 1)
    def test_campos_obrigatorios(self):
        with self.assertRaises(TarefaInvalida): preparar_fila([{'tipo':'GUIA'}])
    def test_nao_vazar_dados_no_painel(self):
        texto = str(gerar_preview([EXEMPLO]))
        for sigilo in ('PESSOA_PRIVADA', 'NUMERO_PRIVADO', 'DETALHE_PRIVADO'):
            self.assertNotIn(sigilo, texto)
    def test_execucao_e_notificacao_bloqueadas(self):
        t = gerar_preview([EXEMPLO])['tarefas'][0]
        self.assertFalse(t['execucao_permitida'])
        self.assertFalse(t['notificacao_permitida'])
    def test_fonte_real_bloqueada(self):
        with self.assertRaises(FonteNaoHomologada): preparar_fila([EXEMPLO], fonte_homologada=True)

if __name__ == '__main__': unittest.main()
