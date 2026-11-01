"""Consulta publica de processo na API Publica do DataJud (CNJ) - somente metadados publicos.

Usa DATAJUD_API_KEY / DATAJUD_BASE_URL do .env (chave publica divulgada pelo CNJ).
Falha NUNCA vira "nada encontrado": levanta erro para a IA avisar a pessoa.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

UFS = ("ac", "al", "ap", "am", "ba", "ce", "dft", "es", "go", "ma", "mt", "ms", "mg", "pa", "pb", "pr",
       "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "se", "sp", "to")


class ConsultaErro(RuntimeError):
    pass


def indice(cnj20: str) -> str:
    """Indice DataJud a partir do segmento J.TR do numero CNJ."""
    j, tr = cnj20[13], int(cnj20[14:16])
    if j == "8" and 1 <= tr <= 27:
        return "api_publica_tj" + UFS[tr - 1]
    if j == "5":
        return f"api_publica_trt{tr}"
    if j == "4":
        return f"api_publica_trf{tr}"
    if j == "3":
        return "api_publica_stj"
    if j == "6" and 1 <= tr <= 27:
        return "api_publica_tre-" + UFS[tr - 1].replace("dft", "df")
    raise ConsultaErro("TRIBUNAL_NAO_SUPORTADO")


def consultar(numero_cnj: str, post=None) -> dict:
    dig = re.sub(r"\D", "", numero_cnj or "")
    if len(dig) != 20:
        return {"erro": "número CNJ inválido (precisa de 20 dígitos)"}
    chave = os.environ.get("DATAJUD_API_KEY", "").strip()
    if not chave:
        return {"disponivel": False, "mensagem": "Consulta pública (DataJud) não configurada no robô "
                                                 "(falta DATAJUD_API_KEY no .env)."}
    base = (os.environ.get("DATAJUD_BASE_URL") or "https://api-publica.datajud.cnj.jus.br").rstrip("/")
    url = f"{base}/{indice(dig)}/_search"
    corpo = json.dumps({"query": {"match": {"numeroProcesso": dig}}, "size": 3}).encode()
    req = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Authorization": f"APIKey {chave}", "Content-Type": "application/json"})
    if post:
        data = post(req)
    else:
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read(3_000_000))
        except urllib.error.HTTPError as exc:
            raise ConsultaErro(f"DATAJUD_HTTP_{exc.code}") from None
    hits = (data.get("hits") or {}).get("hits") or []
    if not hits:
        return {"encontrado": False, "fonte": "DataJud/CNJ (dados públicos)",
                "mensagem": "Processo não localizado na base pública do DataJud (pode estar em segredo de "
                            "justiça, ser muito recente ou ainda não ter sido enviado pelo tribunal)."}
    src = hits[0].get("_source") or {}
    movs = sorted(src.get("movimentos") or [], key=lambda m: m.get("dataHora") or "", reverse=True)[:6]
    return {
        "encontrado": True, "fonte": "DataJud/CNJ (dados públicos; podem ter atraso em relação ao tribunal)",
        "tribunal": src.get("tribunal"), "grau": src.get("grau"),
        "classe": (src.get("classe") or {}).get("nome"),
        "orgao_julgador": (src.get("orgaoJulgador") or {}).get("nome"),
        "assuntos": [a.get("nome") for a in (src.get("assuntos") or []) if isinstance(a, dict)][:5],
        "data_ajuizamento": src.get("dataAjuizamento"),
        "ultima_atualizacao": src.get("dataHoraUltimaAtualizacao"),
        "ultimas_movimentacoes": [{"data": m.get("dataHora"), "movimento": m.get("nome")} for m in movs],
    }
