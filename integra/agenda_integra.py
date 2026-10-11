"""Consulta somente leitura da Agenda INTEGRA (Etapa 64).

O POST /moderno/modulo/12/agendaListar.asp foi confirmado pelo supervisor.
A estrutura HTML de linhas preenchidas ainda NÃO foi homologada.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from selenium.webdriver.remote.webdriver import WebDriver

ENDPOINT = "/moderno/modulo/12/agendaListar.asp"
STATUS_VALIDOS = {"CONCLUIDO", "NAOCONCLUIDO", "VISUALIZADO", "NAOVISUALIZADO"}
FORM_ID = "formAgendaCalendario"


class AgendaErro(RuntimeError):
    """Falha de consulta ou resposta inesperada da Agenda."""


class AgendaSessaoExpirada(AgendaErro):
    """Sessão ausente ou expirada."""


class AgendaParserNaoHomologado(AgendaErro):
    """Há registros, mas o parser de linhas não foi homologado."""


def _data(valor: date | datetime | str) -> date:
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    if isinstance(valor, str):
        for formato in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(valor, formato).date()
            except ValueError:
                pass
    raise ValueError("Data inválida: use date, dd/mm/aaaa ou aaaa-mm-dd")


def _validar_origem(driver: WebDriver) -> None:
    url = urlparse(driver.current_url)
    if url.scheme != "https" or not url.hostname:
        raise AgendaErro("Abra primeiro a Agenda autenticada em HTTPS")


def _consultar_fragmento(driver: WebDriver, inicio: date, fim: date,
                         status: str | None, tipo: str | None) -> str:
    """Consulta POST same-origin; não modifica o DOM nem submete o formulário."""
    _validar_origem(driver)
    script = r"""
        const [endpoint, ini, fim, status, tipo, done] = arguments;
        const form = document.getElementById('formAgendaCalendario');
        if (!form) { done({error: 'FORMULARIO_NAO_ENCONTRADO'}); return; }
        const params = new URLSearchParams(new FormData(form));
        const obrigatorios = ['hdAtivo','hdEscritorioUsuario','hdModeloAgenda'];
        const ausentes = obrigatorios.filter(k => !params.has(k));
        if (ausentes.length) { done({error: 'CAMPOS_AUSENTES: ' + ausentes.join(',')}); return; }
        if (params.get('hdAtivo') !== '1') {
            done({error: 'HD_ATIVO_INVALIDO'}); return;
        }
        // Reutiliza todos os demais valores presentes na página, sem hardcode de usuário.
        params.set('txtDataInicial', ini);
        params.set('txtDataFinal', fim);
        params.set('hdDataDiaSelecionado', ini);
        params.set('hdTipoData', 'aDataMenu2'); // modo Semana; datas explícitas prevalecem
        params.set('mesCalendario', String(Number(ini.slice(3, 5))));
        params.set('anoCalendario', ini.slice(6, 10));
        params.set('hdStatus', status === null ? '' : status);
        params.set('hdTipo', tipo === null ? '' : tipo);
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);
        fetch(endpoint, {
            method: 'POST',
            credentials: 'same-origin',
            redirect: 'follow',
            headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                      'X-Requested-With': 'XMLHttpRequest'},
            body: params.toString(), signal: controller.signal
        }).then(async response => {
            const html = await response.text();
            const destino = new URL(response.url, location.href);
            done({status: response.status, url_path: destino.pathname,
                  html: html, content_type: response.headers.get('content-type') || ''});
        }).catch(e => done({error: e.name === 'AbortError' ? 'TIMEOUT' : 'FALHA_DE_REDE'}))
          .finally(() => clearTimeout(timeout));
    """
    try:
        # Aguardamos até 25 s para o fetch com timeout interno de 20 s.
        driver.set_script_timeout(25)
        result = driver.execute_async_script(script, ENDPOINT,
                                             inicio.strftime('%d/%m/%Y'),
                                             fim.strftime('%d/%m/%Y'), status, tipo)
    except Exception as exc:
        raise AgendaErro("Falha ou timeout ao consultar a Agenda") from exc
    if not isinstance(result, dict):
        raise AgendaErro("Resposta de execução inválida")
    if result.get('error'):
        raise AgendaErro("Consulta não executada: " + result['error'])
    if result.get('status') in (401, 403):
        raise AgendaSessaoExpirada("Sessão expirada ou acesso negado")
    if result.get('status') != 200:
        raise AgendaErro(f"HTTP inesperado na consulta: {result.get('status')}")
    if result.get('url_path') != ENDPOINT:
        raise AgendaSessaoExpirada("Consulta redirecionada; verifique a sessão")
    return result.get('html', '')


def _total(texto: str) -> tuple[int, int] | None:
    m = re.search(r'exibindo\s+(\d+)\s+de\s+(\d+)', texto, flags=re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def interpretar_fragmento(html: str) -> list[dict]:
    """Reconhece vazio; falha fechada para linhas reais ainda não homologadas."""
    if not html or len(html.strip()) < 20:
        raise AgendaErro("Resposta curta ou vazia, possivelmente sessão expirada")
    soup = BeautifulSoup(html, 'html.parser')
    if soup.find('form', attrs={'id': re.compile('login', re.I)}) or soup.find('input', attrs={'type': 'password'}):
        raise AgendaSessaoExpirada("Página de autenticação recebida no lugar da Agenda")
    texto = soup.get_text(' ', strip=True)
    vazio = soup.select_one('div.even.empty')
    if vazio and 'Você não possui agendamento nesse período' in vazio.get_text(' ', strip=True):
        total = _total(texto)
        if total and total != (0, 0):
            raise AgendaErro("Inconsistência: listagem vazia com total não zero")
        return []
    total = _total(texto)
    if total is None:
        raise AgendaErro("Resposta inesperada: não contém 'exibindo N de N' nem marcador vazio")
    exibidos, encontrados = total
    if exibidos == 0 and encontrados == 0:
        # Sem marcador .empty, não assumir vazio (resposta possivelmente incompleta).
        raise AgendaErro("Total zero sem marcador .even.empty confirmado")
    if encontrados < exibidos:
        raise AgendaErro("Contagem de registros inconsistente")
    # PENDENTE DE HOMOLOGAÇÃO: nenhuma linha preenchida foi disponibilizada.
    # Não inferir seletores/campos ou devolver dados incorretos.
    raise AgendaParserNaoHomologado(
        f"Listagem contém {exibidos} de {encontrados} registros; "
        "parser de linhas e paginação pendentes de homologação")


class AgendaIntegra:
    def __init__(self, driver: WebDriver):
        self.driver = driver

    def listar_tarefas(self, data_inicio: date | datetime | str,
                      data_fim: date | datetime | str,
                      status: str | None = None,
                      tipo: str | None = None) -> list[dict]:
        inicio, fim = _data(data_inicio), _data(data_fim)
        if inicio > fim:
            raise ValueError("data_inicio deve ser anterior ou igual a data_fim")
        if status is not None:
            status = status.upper().strip()
            if status not in STATUS_VALIDOS:
                raise ValueError("Status inválido")
        if tipo is not None and (not isinstance(tipo, str) or not tipo.strip()):
            raise ValueError("Tipo deve ser uma string não vazia")
        html = _consultar_fragmento(self.driver, inicio, fim, status, tipo)
        return interpretar_fragmento(html)


def listar_tarefas(driver: WebDriver, data_inicio: date | datetime | str,
                   data_fim: date | datetime | str,
                   status: str | None = None, tipo: str | None = None) -> list[dict]:
    """API funcional para quem já possui uma instância Selenium autenticada."""
    return AgendaIntegra(driver).listar_tarefas(data_inicio, data_fim, status, tipo)


def salvar_amostra_mascarada(html: str, destino: str | Path = 'amostra_agenda_mascarada.txt') -> Path:
    """Grava APENAS estrutura de tags/atributos permitidos, sem texto, links ou valores.

    Use somente após confirmar que a resposta contém registros reais.
    A saída não inclui atributos href, data-*, onclick, value, title, src ou style.
    """
    soup = BeautifulSoup(html, 'html.parser')
    root = soup.select_one('#divPesquisaAgendaListar') or soup.select_one('#cardListagem') or soup
    linhas: list[str] = ['AMOSTRA ESTRUTURAL — textos e valores omitidos']
    limite = 350

    def walk(node: Tag, nivel: int = 0) -> None:
        if len(linhas) >= limite or nivel > 10:
            return
        # Classes podem conter dados dinâmicos; exportar somente nomes seguros e estáticos.
        classes = [c for c in node.get('class', []) if re.fullmatch(r'[A-Za-z_-]{1,32}', c)]
        tag = node.name if re.fullmatch(r'[a-z][a-z0-9-]*', node.name or '') else 'elemento'
        linhas.append('  ' * nivel + tag + ('.' + '.'.join(classes[:4]) if classes else '') +
                      f' [filhos={len(node.find_all(recursive=False))}; texto=XXXXX]')
        for filho in node.find_all(recursive=False)[:12]:
            walk(filho, nivel + 1)

    if isinstance(root, Tag):
        walk(root)
    caminho = Path(destino)
    caminho.write_text('\n'.join(linhas) + '\n', encoding='utf-8')
    return caminho
