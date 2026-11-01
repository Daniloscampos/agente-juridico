"""Teste local de acesso. Não importa nem executa o fluxo main.py."""
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
LOGIN_URL = "https://www.integra.adv.br/login-integra.asp"


def origem_permitida(url):
    try:
        u = urlsplit(url)
        return (u.scheme == "https" and u.hostname == "www.integra.adv.br"
                and u.port in (None, 443) and u.username is None and u.password is None)
    except ValueError:
        return False


def evidencias_acesso(url, texto, tem_campo_senha):
    # Indícios da interface observada; não comprovam permissões por módulo.
    return (origem_permitida(url)
            and urlsplit(url).path.startswith("/moderno/")
            and not tem_campo_senha
            and all(label in texto.casefold() for label in ("clientes", "processos", "agenda")))


def exigir_agente_ativo(control):
    if control.is_paused():
        raise RuntimeError("Agente pausado: teste interrompido. Confira o painel de supervisão.")


def executar():
    # Sem ler .env, capturar senhas ou preencher formulários.
    from core import control
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.common.exceptions import WebDriverException

    exigir_agente_ativo(control)
    report_dir = ROOT / "saida"
    report_dir.mkdir(exist_ok=True)
    lock = ROOT / ".teste-integra.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise RuntimeError("Outro teste está aberto. Feche-o antes de tentar novamente. Se houve travamento, remova .teste-integra.lock apenas depois de fechar o navegador do teste.") from None
    os.close(fd)
    driver = None
    status = "NAO_VERIFICADO"
    detalhe = "O acesso não foi confirmado."
    try:
        options = Options()
        # Perfil separado do conector de produção; persiste a sessão local.
        profile = ROOT / ".browser" / "teste-integra"
        profile.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--start-maximized")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        exigir_agente_ativo(control)
        driver.get(LOGIN_URL)
        print("No Chrome que abriu, entre manualmente com a conta autorizada do agente.")
        print("O teste aguarda até 5 minutos. Ctrl+C cancela. Não envie a senha ao chat.")
        deadline = time.monotonic() + 300
        consecutive = 0
        while time.monotonic() < deadline:
            exigir_agente_ativo(control)
            url = driver.current_url
            if not origem_permitida(url):
                raise RuntimeError("O navegador saiu da origem esperada. Teste interrompido sem confirmar acesso.")
            body = driver.find_element(By.TAG_NAME, "body").text
            password = any(el.is_displayed() for el in driver.find_elements(By.CSS_SELECTOR, 'input[type="password"]'))
            if evidencias_acesso(url, body, password):
                consecutive += 1
            else:
                consecutive = 0
            if consecutive >= 2:
                status = "ACESSO_VERIFICADO"
                detalhe = "Área interna observada com Clientes, Processos e Agenda. Leitura de tarefas e escrita não testadas."
                break
            time.sleep(1)
        if status != "ACESSO_VERIFICADO":
            detalhe = "Tempo esgotado sem evidências suficientes. Isso não significa que a senha esteja incorreta."
    except KeyboardInterrupt:
        status, detalhe = "CANCELADO", "Teste cancelado pelo operador."
    except RuntimeError as exc:
        detalhe = str(exc)
    except WebDriverException:
        # Nunca serializar exceções do navegador: podem conter dados da página.
        detalhe = "Falha no Chrome/driver, carregamento ou leitura da interface. Confira a conexão e o Chrome instalado."
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException:
                pass
        lock.unlink(missing_ok=True)
        stamp = datetime.now(timezone.utc)
        report = report_dir / ("teste_integra_" + stamp.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
        report.write_text(json.dumps({"data_utc": stamp.isoformat(), "status": status,
            "detalhe": detalhe, "escopo": "acesso_manual",
            "tarefas_lidas": False, "alteracoes_em_tarefas": False},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(status + ": " + detalhe)
        print("Relatório: " + str(report))
    return 0 if status == "ACESSO_VERIFICADO" else 1


if __name__ == "__main__":
    try:
        sys.exit(executar())
    except ImportError:
        print("Dependências ou core.control ausentes. Copie este script para a raiz agente-juridico e use o Python da .venv do projeto.")
        sys.exit(2)
    except RuntimeError as exc:
        print(str(exc))
        sys.exit(2)
