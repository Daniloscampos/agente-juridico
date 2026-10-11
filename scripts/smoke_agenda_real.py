"""Smoke real e somente leitura: login manual, consulta do mês corrente.

Saída normal: STATUS=VAZIO QUANTIDADE=0 ou STATUS=OK QUANTIDADE=N.
Nunca imprime HTML, nomes de clientes ou processos.
"""
from __future__ import annotations
import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Permite rodar diretamente de scripts/ sem instalar o projeto como pacote.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from integra.agenda_integra import AgendaIntegra, AgendaSessaoExpirada, AgendaParserNaoHomologado, AgendaErro

def main() -> int:
    url = os.environ.get('INTEGRA_URL', '').strip()
    if not url:
        url = input('URL HTTPS do INTEGRA (sem credenciais): ').strip()
    if not url.startswith('https://'):
        print('STATUS=ERRO QUANTIDADE=0')
        return 2
    opts = Options()
    driver = webdriver.Chrome(options=opts)
    try:
        driver.get(url)
        input('Faça login manual e abra a Agenda; pressione Enter para consultar... ')
        try:
            WebDriverWait(driver, 20).until(
                lambda d: d.execute_script("return !!document.getElementById('formAgendaCalendario')")
            )
        except Exception:
            print('STATUS=ERRO_SESSAO QUANTIDADE=0')
            return 3
        hoje = date.today()
        inicio = hoje.replace(day=1)
        fim = (inicio.replace(year=inicio.year + 1, month=1) if inicio.month == 12
               else inicio.replace(month=inicio.month + 1)) - timedelta(days=1)
        try:
            registros = AgendaIntegra(driver).listar_tarefas(inicio, fim)
        except AgendaSessaoExpirada:
            print('STATUS=ERRO_SESSAO QUANTIDADE=0')
            return 3
        except AgendaParserNaoHomologado:
            # Não assumir registros válidos antes da homologação do parser.
            print('STATUS=ERRO_PARSER QUANTIDADE=0')
            return 4
        except AgendaErro:
            print('STATUS=ERRO QUANTIDADE=0')
            return 5
        print(f"STATUS={'VAZIO' if not registros else 'OK'} QUANTIDADE={len(registros)}")
        return 0
    finally:
        driver.quit()

if __name__ == '__main__':
    raise SystemExit(main())
