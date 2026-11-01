"""Leitura da listagem de publicacoes do INTEGRA (resposta de publicacoesListar.asp).

Somente interpreta HTML ja carregado. Nao abre publicacoes, nao chama
clickVisualizar() e nao altera nada no INTEGRA. Usa apenas a biblioteca padrao.

Estrutura validada em 08/10/2026 (arquivo publicacoes_integra.txt):
  <tbody><tr>
    td[0]  checkbox  name="chkPublicacaoLista" value="<codigo>"
    td[3]  "D dd/mm/aaaa" (disponibilizacao) e "I dd/mm/aaaa hh:mm:ss" (inclusao)
    td[4]  <p title="Justica ...">  <p title="<orgao completo>">orgao - comarca</p>
    td[5]  pares de <p>: cliente X parte adversa | numero CNJ (pode haver varios
           processos ou nenhum = "vinculo pendente")
  </tr></tbody>
  rodape: "Exibindo N de M"
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from html.parser import HTMLParser
import re

CNJ_RE = re.compile(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b")
DATA_RE = re.compile(r"\b(\d{2}/\d{2}/\d{4})\b")
HORA_RE = re.compile(r"\b(\d{2}:\d{2}:\d{2})\b")
TOTAL_RE = re.compile(r"Exibindo\s+(\d+)\s+de\s+(\d+)", re.I)
CODIGO_RE = re.compile(r"codigo=(\d+)")

STATUS_OK = "vinculada"
STATUS_PENDENTE = "vinculo_pendente"


class EstruturaInesperada(ValueError):
    """O HTML nao corresponde ao layout validado. O robo deve parar, nao adivinhar."""


@dataclass
class Processo:
    numero_cnj: str
    cliente: str = ""
    parte_adversa: str = ""
    codigo_processo_integra: str = ""


@dataclass
class Publicacao:
    codigo: str
    data_disponibilizacao: str = ""
    data_inclusao: str = ""
    hora_inclusao: str = ""
    justica: str = ""
    orgao: str = ""
    orgao_comarca: str = ""
    processos: list[Processo] = field(default_factory=list)

    @property
    def status_vinculo(self) -> str:
        return STATUS_OK if self.processos else STATUS_PENDENTE

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status_vinculo"] = self.status_vinculo
        return d


@dataclass
class ResultadoListagem:
    publicacoes: list[Publicacao]
    exibindo: int | None
    total: int | None

    @property
    def completo(self) -> bool:
        """True quando o rodape confirma que todas as linhas estao na pagina."""
        return self.total is not None and self.exibindo == self.total == len(self.publicacoes)


def _limpa(texto: str) -> str:
    return re.sub(r"\s+", " ", texto or "").strip()


class _ListagemParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_tbody = False
        self.row: list[dict] | None = None
        self.cell: dict | None = None
        self.rows: list[list[dict]] = []
        self.texto_total: list[str] = []
        self._p: dict | None = None
        self._u: dict | None = None
        self._span_x = False

    # -- tags ---------------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "tbody":
            self.in_tbody = True
        elif not self.in_tbody:
            return
        elif tag == "tr":
            self.row = []
        elif tag == "td" and self.row is not None:
            self.cell = {"text": [], "inputs": [], "ps": []}
            self.row.append(self.cell)
        elif self.cell is None:
            return
        elif tag == "input":
            self.cell["inputs"].append(a)
        elif tag == "p":
            self._p = {"title": a.get("title", ""), "text": [], "us": [], "has_x": False}
            self.cell["ps"].append(self._p)
        elif tag == "u" and self._p is not None:
            self._u = {"title": a.get("title", ""), "onclick": a.get("onclick", ""), "text": []}
            self._p["us"].append(self._u)
        elif tag == "span" and self._p is not None:
            self._span_x = True

    def handle_endtag(self, tag):
        if tag == "tbody":
            self.in_tbody = False
        elif tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "td":
            self.cell = None
        elif tag == "p":
            self._p = None
        elif tag == "u":
            self._u = None
        elif tag == "span":
            self._span_x = False

    def handle_data(self, data):
        if not self.in_tbody:
            self.texto_total.append(data)
            return
        if self.cell is not None:
            self.cell["text"].append(data)
        if self._p is not None:
            self._p["text"].append(data)
            if self._span_x and _limpa(data).upper() == "X":
                self._p["has_x"] = True
        if self._u is not None:
            self._u["text"].append(data)


def _processos(cell: dict) -> list[Processo]:
    processos: list[Processo] = []
    partes: tuple[str, str] = ("", "")
    for p in cell["ps"]:
        us = p["us"]
        if p["has_x"] and len(us) >= 2:
            # title traz o nome completo; o texto visivel pode vir truncado com "..."
            partes = (_limpa(us[0]["title"] or "".join(us[0]["text"])),
                      _limpa(us[1]["title"] or "".join(us[1]["text"])))
            continue
        for u in us:
            m = CNJ_RE.search(u["title"] or "") or CNJ_RE.search("".join(u["text"]))
            if not m:
                continue
            cod = CODIGO_RE.search(u["onclick"] or "")
            processos.append(Processo(numero_cnj=m.group(1), cliente=partes[0], parte_adversa=partes[1],
                                      codigo_processo_integra=cod.group(1) if cod else ""))
            partes = ("", "")
    return processos


def parse_listagem(html: str) -> ResultadoListagem:
    if not html or "<tbody" not in html.lower():
        m = TOTAL_RE.search(html or "")
        if m and m.group(1) == m.group(2) == "0":
            return ResultadoListagem(publicacoes=[], exibindo=0, total=0)
        raise EstruturaInesperada("LISTAGEM_SEM_TBODY")
    parser = _ListagemParser()
    parser.feed(html)
    parser.close()

    publicacoes: list[Publicacao] = []
    vistos: set[str] = set()
    for row in parser.rows:
        if len(row) < 6:
            raise EstruturaInesperada(f"LINHA_COM_{len(row)}_COLUNAS")
        codigo = ""
        for inp in row[0]["inputs"]:
            if inp.get("name") == "chkPublicacaoLista" and str(inp.get("value", "")).isdigit():
                codigo = inp["value"]
        if not codigo:
            raise EstruturaInesperada("LINHA_SEM_CODIGO")
        if codigo in vistos:
            continue
        vistos.add(codigo)

        datas_txt = " ".join(row[3]["text"])
        datas = DATA_RE.findall(datas_txt)
        hora = HORA_RE.search(datas_txt)

        ps = row[4]["ps"]
        justica = _limpa(ps[0]["title"] or "".join(ps[0]["text"])) if ps else ""
        orgao = _limpa(ps[1]["title"]) if len(ps) > 1 else ""
        orgao_comarca = _limpa("".join(ps[1]["text"])) if len(ps) > 1 else ""

        publicacoes.append(Publicacao(
            codigo=codigo,
            data_disponibilizacao=datas[0] if datas else "",
            data_inclusao=datas[1] if len(datas) > 1 else "",
            hora_inclusao=hora.group(1) if hora else "",
            justica=justica,
            orgao=orgao,
            orgao_comarca=orgao_comarca,
            processos=_processos(row[5]),
        ))

    m = TOTAL_RE.search(" ".join(parser.texto_total))
    exibindo, total = (int(m.group(1)), int(m.group(2))) if m else (None, None)
    return ResultadoListagem(publicacoes=publicacoes, exibindo=exibindo, total=total)
