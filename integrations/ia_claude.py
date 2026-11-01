"""IA (Claude, Anthropic) para o atendente de WhatsApp - SOMENTE equipe interna.

Chamada direta a API HTTP (sem SDK; nada a instalar). A chave fica so no .env
(ANTHROPIC_API_KEY), nunca e impressa.

O Claude NAO acessa o INTEGRA diretamente: ele so pode chamar as 4 ferramentas de
CONSULTA abaixo, executadas pelo proprio robo (mesmas regras de leitura/pausa).
Nao existe ferramenta de escrita: protocolar, assinar, pagar, marcar como lida,
apagar ou falar com cliente continua impossivel.

Variaveis (.env):
  WA_IA_ENABLED=true          liga a IA no atendente (padrao: desligada)
  ANTHROPIC_API_KEY=...       chave da API (configurar com scripts/configurar_ia.py)
  IA_MODELO=claude-sonnet-5-5 modelo (qualquer modelo atual com visao)
  IA_MAX_TOKENS=1024
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_RODADAS = 5            # limite de chamadas de ferramenta por pedido
MAX_RESULTADO = 12000      # caracteres devolvidos por ferramenta ao modelo

from integrations.ia_persona import PERSONA as SYSTEM  # noqa: E402  (persona unica em ia_persona.py)

FERRAMENTAS = [
    {"name": "publicacoes_hoje",
     "description": "Consulta AO VIVO no INTEGRA as publicações de hoje (lista completa da tela de publicações).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "publicacoes_por_processo",
     "description": "Publicações já lidas pelo robô para um número de processo CNJ "
                    "(formato 0000000-00.0000.0.00.0000; aceita só dígitos).",
     "input_schema": {"type": "object", "properties": {"numero_cnj": {"type": "string"}},
                      "required": ["numero_cnj"]}},
    {"name": "publicacoes_por_data",
     "description": "Publicações já lidas pelo robô com data de disponibilização ou inclusão DD/MM/AAAA.",
     "input_schema": {"type": "object", "properties": {"data": {"type": "string", "description": "DD/MM/AAAA"}},
                      "required": ["data"]}},
    {"name": "publicacoes_sem_vinculo",
     "description": "Publicações já lidas pelo robô que estão SEM processo vinculado no INTEGRA.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "consulta_publica_processo",
     "description": "Dados PÚBLICOS do processo na base DataJud do CNJ: tribunal, classe, órgão julgador, "
                    "assuntos, data de ajuizamento e últimas movimentações. Pode ter atraso em relação ao tribunal.",
     "input_schema": {"type": "object", "properties": {"numero_cnj": {"type": "string"}},
                      "required": ["numero_cnj"]}},
    {"name": "agenda_prazos",
     "description": "Agenda, prazos e audiências do INTEGRA para um período (DD/MM/AAAA).",
     "input_schema": {"type": "object", "properties": {"data_inicio": {"type": "string"},
                                                       "data_fim": {"type": "string"}}}},
]


class IAErro(RuntimeError):
    pass


def _int(valor, padrao: int) -> int:
    try:
        return max(64, int(str(valor).strip()))
    except (TypeError, ValueError):
        return padrao


def config() -> dict:
    return {
        "ATIVA": os.environ.get("WA_IA_ENABLED", "").strip().lower() == "true",
        "CHAVE": os.environ.get("ANTHROPIC_API_KEY", "").strip(),
        "MODELO": os.environ.get("IA_MODELO", "").strip() or "claude-sonnet-5-5",
        "MAX_TOKENS": _int(os.environ.get("IA_MAX_TOKENS"), 1024),
    }


def problemas(c: dict | None = None) -> list[str]:
    c = c or config()
    erros = []
    if not c["CHAVE"] or len(c["CHAVE"]) < 20 or " " in c["CHAVE"]:
        erros.append("ANTHROPIC_API_KEY vazia/invalida (rode scripts\\configurar_ia.py)")
    return erros


def _post(payload: dict, c: dict) -> dict:
    corpo = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=corpo, method="POST", headers={
        "x-api-key": c["CHAVE"], "anthropic-version": API_VERSION, "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:   # mostra so o codigo/tipo (nunca a chave)
        try:
            erro = json.loads(exc.read() or b"{}").get("error", {}) or {}
            tipo = str(erro.get("type", ""))
            msg = str(erro.get("message", ""))[:160]
        except Exception:
            tipo, msg = "", ""
        raise IAErro(f"HTTP {exc.code} {tipo}".strip() + (f": {msg}" if msg else "")) from None


def teste_rapido(c: dict | None = None, post=None) -> str:
    """Chamada minima para validar chave e modelo. Devolve o modelo que respondeu."""
    c = c or config()
    resp = (post or _post)({"model": c["MODELO"], "max_tokens": 8,
                            "messages": [{"role": "user", "content": "Responda só: ok"}]}, c)
    return str(resp.get("model") or c["MODELO"])


def _texto(blocos) -> str:
    return "\n".join(b.get("text", "") for b in blocos if b.get("type") == "text").strip()


def responder(texto: str, ferramentas: dict, imagem: tuple[str, str] | None = None,
              historico: list | None = None, c: dict | None = None, post=None,
              pessoa: str = "", cumprimentar: bool = False, modo: str = "completo") -> str:
    """texto: pedido (ou transcricao do audio); imagem: (base64, media_type) opcional;
    ferramentas: {nome: funcao(**args) -> dict/list serializavel}; historico: mensagens anteriores."""
    c = c or config()
    post = post or _post
    from integrations.ia_persona import montar_system
    system = montar_system(pessoa, cumprimentar, modo=modo)
    conteudo = []
    if imagem:
        dados, tipo = imagem
        bloco = "document" if tipo == "application/pdf" else "image"
        conteudo.append({"type": bloco, "source": {"type": "base64", "media_type": tipo, "data": dados}})
    conteudo.append({"type": "text", "text": texto.strip() or "(arquivo sem legenda: descreva e extraia os dados úteis)"})
    mensagens = list(historico or []) + [{"role": "user", "content": conteudo}]

    for _ in range(MAX_RODADAS):
        resp = post({"model": c["MODELO"], "max_tokens": c["MAX_TOKENS"], "system": system,
                     "tools": FERRAMENTAS, "messages": mensagens}, c)
        blocos = resp.get("content") or []
        if resp.get("stop_reason") != "tool_use":
            final = _texto(blocos)
            if not final:
                raise IAErro("RESPOSTA_VAZIA")
            if resp.get("stop_reason") == "max_tokens":
                final += "\n\n(Resposta cortada por tamanho. Peça um recorte menor, por exemplo por data ou processo.)"
            return final
        mensagens.append({"role": "assistant", "content": blocos})
        resultados = []
        for b in blocos:
            if b.get("type") != "tool_use":
                continue
            fn = ferramentas.get(b.get("name"))
            try:
                if fn is None:
                    raise IAErro("FERRAMENTA_DESCONHECIDA")
                saida = json.dumps(fn(**(b.get("input") or {})), ensure_ascii=False)[:MAX_RESULTADO]
                resultados.append({"type": "tool_result", "tool_use_id": b["id"], "content": saida})
            except Exception as exc:   # erro vira informacao para o modelo (que deve avisar o usuario)
                resultados.append({"type": "tool_result", "tool_use_id": b["id"], "is_error": True,
                                   "content": f"Falha na consulta ({type(exc).__name__}). "
                                              "Não significa que não há publicações."})
        mensagens.append({"role": "user", "content": resultados})
    raise IAErro("LIMITE_DE_CONSULTAS")
