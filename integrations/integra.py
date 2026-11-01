"""Cliente Selenium do INTEGRA/PROMAD — etapa de integracao SOMENTE LEITURA.

O que faz:
  * abre um Chrome com perfil exclusivo do robo;
  * entra no INTEGRA (login manual por padrao; automatico so com conta tecnica);
  * confirma a area interna (menus Clientes, Processos e Agenda);
  * abre Publicacoes, aciona "Pesquisar" com o filtro padrao da tela e devolve o
    HTML da listagem para integrations/integra_parser.py.

O que NAO faz (bloqueado no codigo):
  * abrir publicacoes ou chamar clickVisualizar() (pode marcar como lida);
  * escrever observacoes, concluir tarefas ou alterar qualquer registro;
  * protocolar, assinar, pagar ou usar certificado do advogado.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from core.audit import get_logger
from core.config import settings
from core.policy import Blocked

log = get_logger("integra")

# Seletores validados manualmente em 08/10/2026 -----------------------------
CAMPO_USUARIO = "txtUsuario"
CAMPO_SENHA = "txtSenha"
MENUS_AREA_INTERNA = ("Clientes", "Processos", "Agenda")
MENU_PUBLICACOES = "Publicações"
BOTAO_PESQUISAR_XPATH = ("//button[normalize-space()='Pesquisar'] | "
                         "//input[@type='button' or @type='submit'][@value='Pesquisar'] | "
                         "//a[normalize-space()='Pesquisar']")
BOTAO_PESQUISAR_FORM_XPATH = ("//form[@id='frmPublicacaoPesquisar']//*[self::button or self::a][normalize-space()='Pesquisar'] | "
                              "//form[@id='frmPublicacaoPesquisar']//input[@value='Pesquisar']")
CONTAINER_LISTA = "divListaPublicacoes"

# Observa (somente leitura) a resposta da consulta de publicacoes feita pela propria tela.
HOOK_RESPOSTA_JS = """
window.__roboPubResp = null;
if (!window.__roboPubHook) {
  window.__roboPubHook = true;
  var o = XMLHttpRequest.prototype.open, s = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__roboUrl = String(u || ''); return o.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    var x = this;
    x.addEventListener('load', function () {
      if (x.__roboUrl.toLowerCase().indexOf('publicacoeslistar') >= 0 && x.status === 200) {
        window.__roboPubResp = x.responseText;
      }
    });
    return s.apply(this, arguments);
  };
}
"""
MENSAGEM_SESSAO_INVALIDA = "Faça o login novamente"


class IntegraIndisponivel(Blocked):
    """Falha de acesso/leitura. Nunca deve ser tratada como 'zero publicacoes'."""


class IntegraClient:
    def __init__(self, user_data_dir: str | None = None, driver=None):
        self.user_data_dir = user_data_dir or settings.INTEGRA_PROFILE_DIR
        self.driver = driver          # permite injetar um driver falso nos testes
        self._driver_proprio = driver is None

    # -- ciclo de vida ------------------------------------------------------
    def __enter__(self):
        if self.driver is None:
            self.driver = self._novo_chrome()
        return self

    def __exit__(self, *exc):
        if self.driver is not None and self._driver_proprio:
            try:
                self.driver.quit()
            except Exception:
                pass

    def _novo_chrome(self):
        from selenium import webdriver
        from selenium.common.exceptions import SessionNotCreatedException
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service

        perfil = Path(self.user_data_dir).resolve()
        perfil.mkdir(parents=True, exist_ok=True)
        opts = Options()
        opts.add_argument(f"--user-data-dir={perfil}")
        opts.add_argument("--start-maximized")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        if settings.INTEGRA_HEADLESS:
            opts.add_argument("--headless=new")
        service = Service(settings.CHROME_DRIVER_PATH) if settings.CHROME_DRIVER_PATH else None
        try:
            driver = webdriver.Chrome(options=opts, service=service) if service else webdriver.Chrome(options=opts)
        except SessionNotCreatedException as exc:
            # Erro registrado em erro.txt: "Chrome instance exited" = perfil ja aberto em outro Chrome.
            raise IntegraIndisponivel(
                "CHROME_NAO_INICIOU: feche janelas antigas do robo (perfil "
                f"{perfil}) ou defina outro INTEGRA_PROFILE_DIR") from exc
        driver.set_page_load_timeout(max(settings.SELENIUM_TIMEOUT, 30))
        return driver

    # -- utilitarios --------------------------------------------------------
    def _by(self):
        from selenium.webdriver.common.by import By
        return By

    def _texto_pagina(self) -> str:
        try:
            return self.driver.find_element(self._by().TAG_NAME, "body").text or ""
        except Exception:
            return ""

    def area_interna_visivel(self) -> bool:
        texto = self._texto_pagina()
        if MENSAGEM_SESSAO_INVALIDA.lower() in texto.lower():
            return False
        return all(m in texto for m in MENUS_AREA_INTERNA)

    # -- login --------------------------------------------------------------
    def login(self) -> None:
        """Garante sessao valida. Levanta IntegraIndisponivel se nao conseguir."""
        self.driver.get(settings.INTEGRA_LOGIN_URL)
        time.sleep(2)
        if self.area_interna_visivel():
            log.info("INTEGRA: sessao ja ativa no perfil do robo")
            return

        if settings.INTEGRA_LOGIN_MODE == "auto":
            self._login_automatico()
        else:
            log.info("INTEGRA: aguardando login MANUAL na janela do Chrome "
                     f"(ate {settings.INTEGRA_LOGIN_TIMEOUT}s)")

        limite = time.time() + settings.INTEGRA_LOGIN_TIMEOUT
        while time.time() < limite:
            if self.area_interna_visivel():
                log.info("INTEGRA: ACESSO_VERIFICADO (Clientes, Processos e Agenda visiveis)")
                return
            time.sleep(2)
        raise IntegraIndisponivel("LOGIN_NAO_CONFIRMADO")

    def _login_automatico(self) -> None:
        if not settings.INTEGRA_USER or not settings.INTEGRA_PASS:
            raise IntegraIndisponivel("CREDENCIAIS_AUSENTES_NO_ENV")
        from selenium.webdriver.common.keys import Keys
        By = self._by()
        try:
            usuario = self.driver.find_element(By.ID, CAMPO_USUARIO)
            senha = self.driver.find_element(By.ID, CAMPO_SENHA)
        except Exception:
            try:
                usuario = self.driver.find_element(By.NAME, CAMPO_USUARIO)
                senha = self.driver.find_element(By.NAME, CAMPO_SENHA)
            except Exception as exc:
                raise IntegraIndisponivel("CAMPOS_DE_LOGIN_NAO_ENCONTRADOS") from exc
        usuario.clear()
        usuario.send_keys(settings.INTEGRA_USER)
        senha.clear()
        senha.send_keys(settings.INTEGRA_PASS)
        senha.send_keys(Keys.ENTER)
        log.info("INTEGRA: credenciais da conta tecnica enviadas (valores nao registrados)")

    # -- publicacoes (somente leitura) ---------------------------------------
    # Candidatos ao botao "Pesquisar", do mais especifico ao mais generico.
    PESQUISAR_XPATHS = (
        "//form[@id='frmPublicacaoPesquisar']//*[self::button or self::a or self::input][contains(normalize-space(.),'Pesquisar') or contains(@value,'Pesquisar')]",
        "//*[@onclick and contains(@onclick,'PublicacaoPesquisar')]",
        "//button[contains(normalize-space(.),'Pesquisar')]",
        "//input[(@type='button' or @type='submit') and contains(@value,'Pesquisar')]",
        "//a[contains(normalize-space(.),'Pesquisar')]",
    )

    def _frames(self):
        """Documento principal + iframes (o INTEGRA pode montar telas dentro de iframes)."""
        By = self._by()
        self.driver.switch_to.default_content()
        yield None
        try:
            total = len(self.driver.find_elements(By.TAG_NAME, "iframe"))
        except Exception:
            total = 0
        for i in range(total):
            self.driver.switch_to.default_content()
            try:
                self.driver.switch_to.frame(self.driver.find_elements(By.TAG_NAME, "iframe")[i])
                yield i
            except Exception:
                continue
        self.driver.switch_to.default_content()

    def _tela_publicacoes_visivel(self) -> bool:
        By = self._by()
        for _ in self._frames():
            try:
                if self.driver.find_elements(By.ID, "frmPublicacaoPesquisar") or \
                   self.driver.find_elements(By.ID, CONTAINER_LISTA):
                    return True  # fica posicionado neste frame
            except Exception:
                pass
        self.driver.switch_to.default_content()
        return False

    def abrir_publicacoes(self) -> None:
        By = self._by()
        if settings.INTEGRA_PUBLICACOES_URL:
            self.driver.get(settings.INTEGRA_PUBLICACOES_URL)
        else:
            # Prefere o link do MENU (texto exato), nao o cartao "Publicacoes dos ultimos 30 dias".
            links = [l for l in self.driver.find_elements(By.XPATH,
                     "//a[normalize-space(.)='Publicações' or normalize-space(.)='Publicacoes']") if l.is_displayed()]
            links = links or [l for l in self.driver.find_elements(By.PARTIAL_LINK_TEXT, MENU_PUBLICACOES) if l.is_displayed()]
            if not links:
                raise IntegraIndisponivel("MENU_PUBLICACOES_NAO_ENCONTRADO")
            links[0].click()
        limite = time.time() + max(settings.SELENIUM_TIMEOUT, 30)
        while time.time() < limite:
            self._fechar_aviso_novo_filtro()
            if self._tela_publicacoes_visivel():
                log.info("INTEGRA: tela de Publicacoes aberta")
                return
            time.sleep(1.5)
        raise IntegraIndisponivel("TELA_PUBLICACOES_NAO_ABRIU")

    def _fechar_aviso_novo_filtro(self) -> None:
        """Na 1a abertura o INTEGRA mostra um aviso sobre o novo filtro (modal informativo)."""
        By = self._by()
        for xp in ("//div[contains(@class,'modal') and contains(@class,'show')]//button[contains(.,'Fechar') or contains(.,'Entendi') or contains(.,'OK') or contains(.,'Ok')]",
                   "//div[contains(@class,'modal') and contains(@class,'show')]//button[contains(@class,'close') or @data-dismiss='modal' or @data-bs-dismiss='modal']",
                   "//div[contains(@class,'swal2-popup')]//button[contains(@class,'swal2-confirm')]"):
            try:
                for b in self.driver.find_elements(By.XPATH, xp):
                    if b.is_displayed():
                        b.click()
                        time.sleep(1)
                        return
            except Exception:
                continue

    def _botao_pesquisar(self):
        By = self._by()
        for xp in self.PESQUISAR_XPATHS:
            try:
                vis = [b for b in self.driver.find_elements(By.XPATH, xp) if b.is_displayed()]
            except Exception:
                vis = []
            if vis:
                return vis[-1]
        return None

    def diagnostico(self, motivo: str) -> str:
        """Salva HTML e imagem da tela em saida\\diagnostico_integra_* (uso interno) e
        devolve um resumo SEM dados pessoais: endereco da pagina e botoes visiveis."""
        By = self._by()
        pasta = Path("saida") / f"diagnostico_integra_{time.strftime('%Y%m%d_%H%M%S')}"
        pasta.mkdir(parents=True, exist_ok=True)
        linhas = [f"motivo={motivo}"]
        try:
            self.driver.switch_to.default_content()
            url = (self.driver.current_url or "").split("?")[0]
            linhas.append(f"pagina={url}")
            self.driver.save_screenshot(str(pasta / "tela.png"))
        except Exception:
            pass
        for idx in self._frames():
            nome = "principal" if idx is None else f"iframe{idx}"
            try:
                (pasta / f"{nome}.html").write_text(self.driver.page_source or "", encoding="utf-8")
                botoes = []
                for el in self.driver.find_elements(By.XPATH, "//button | //input[@type='button' or @type='submit'] | //a[@onclick]"):
                    try:
                        if el.is_displayed():
                            t = (el.text or el.get_attribute("value") or el.get_attribute("title") or "").strip()
                            if t and len(t) <= 40:
                                botoes.append(t)
                    except Exception:
                        continue
                tem_form = bool(self.driver.find_elements(By.ID, "frmPublicacaoPesquisar"))
                linhas.append(f"{nome}: form_publicacoes={'sim' if tem_form else 'nao'}; botoes={sorted(set(botoes))[:25]}")
            except Exception:
                continue
        self.driver.switch_to.default_content()
        (pasta / "resumo.txt").write_text("\n".join(linhas), encoding="utf-8")
        log.info(f"INTEGRA: diagnostico salvo em {pasta}")
        return "\n".join(linhas)

    def html_listagem_publicacoes(self, espera: int | None = None) -> str:
        """Aciona a pesquisa (filtro padrao da tela) e devolve o HTML da listagem."""
        By = self._by()
        espera = espera or max(settings.SELENIUM_TIMEOUT, 30)
        if not self._tela_publicacoes_visivel():
            raise IntegraIndisponivel("TELA_PUBLICACOES_NAO_ABRIU")
        # (o metodo acima deixa o driver posicionado no frame da tela de Publicacoes)
        botao = None
        limite = time.time() + 15
        while botao is None and time.time() < limite:
            self._fechar_aviso_novo_filtro()
            botao = self._botao_pesquisar()
            if botao is None:
                time.sleep(1)
        # Captura a RESPOSTA da propria consulta (publicacoesListar.asp) dentro do navegador.
        # Apenas le o que o INTEGRA devolve a tela; nao altera a pagina nem envia nada.
        self.driver.execute_script(HOOK_RESPOSTA_JS)
        try:
            antes = self.driver.find_element(By.ID, CONTAINER_LISTA).get_attribute("innerHTML") or ""
        except Exception:
            antes = ""
        if botao is not None:
            try:
                botao.click()
            except Exception:
                self._fechar_aviso_novo_filtro()  # aviso pode surgir depois e interceptar o clique
                try:
                    self.driver.execute_script("arguments[0].click();", botao)
                except Exception as exc:
                    raise IntegraIndisponivel("CLIQUE_PESQUISAR_BLOQUEADO (aviso/modal aberto?)") from exc
        else:
            # Mesma acao do botao: a funcao de pesquisa da propria tela (somente consulta).
            ok = self.driver.execute_script(
                "if (typeof PublicacaoPesquisar === 'function') { PublicacaoPesquisar(); return true; } return false;")
            if not ok:
                raise IntegraIndisponivel("BOTAO_PESQUISAR_NAO_ENCONTRADO")
            log.info("INTEGRA: pesquisa acionada pela funcao da tela (botao nao localizado)")

        limite = time.time() + espera
        while time.time() < limite:
            if MENSAGEM_SESSAO_INVALIDA.lower() in self._texto_pagina().lower():
                raise IntegraIndisponivel("SESSAO_EXPIRADA")
            try:
                resposta = self.driver.execute_script("return window.__roboPubResp || null;")
            except Exception:
                resposta = None
            if resposta:
                log.info("INTEGRA: resposta de publicacoesListar.asp capturada")
                return resposta
            # Alternativa: listagem montada na tela e diferente da anterior.
            try:
                atual = self.driver.find_element(By.ID, CONTAINER_LISTA).get_attribute("innerHTML") or ""
                if atual != antes and "<tbody" in atual.lower() and re.search(r"Exibindo\s+\d+\s+de\s+\d+", atual, re.I):
                    time.sleep(1)
                    return self.driver.find_element(By.ID, CONTAINER_LISTA).get_attribute("innerHTML") or ""
            except Exception:
                pass
            time.sleep(1)
        raise IntegraIndisponivel("LISTAGEM_NAO_CARREGOU")

    # -- escrita: BLOQUEADA nesta etapa --------------------------------------
    def listar_tarefas(self) -> list:
        raise Blocked("AGENDA_INTEGRA_NAO_MAPEADA: leitura de tarefas ainda nao validada")

    def registrar_retorno(self, tarefa_id: str, status: str, mensagem: str):
        raise Blocked("ESCRITA_NO_INTEGRA_BLOQUEADA_NESTA_ETAPA")

    def concluir_tarefa(self, tarefa_id: str):
        raise Blocked("ESCRITA_NO_INTEGRA_BLOQUEADA_NESTA_ETAPA")

    def visualizar_publicacao(self, codigo: str):
        raise Blocked("ABRIR_PUBLICACAO_BLOQUEADO: clickVisualizar pode marcar como lida")
