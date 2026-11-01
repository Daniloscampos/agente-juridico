"""Cliente minimo da UazAPI (numero conectado em https://uazapi.dev).

Usa somente o TOKEN DA INSTANCIA (header `token`). O token de administracao do
servidor (`admintoken`) NAO e usado nem deve ficar neste computador.

Rotas usadas (docs.uazapi.com):
  GET  {UAZAPI_URL}/instance/status          estado da conexao
  POST {UAZAPI_URL}/send/text                {"number": "5541...", "text": "..."}
  GET  {UAZAPI_URL}/sse?token=...&events=messages   eventos em tempo real (conexao de SAIDA,
                                                    nao precisa abrir porta nem tunel)
  POST {UAZAPI_URL}/message/find             {"chatid": "...@s.whatsapp.net", "limit": 10}
                                             reserva: busca as ultimas mensagens da conversa
                                             (cobre mensagens perdidas quando o SSE cai/trava)
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import re
import time
import urllib.error
import urllib.parse
import urllib.request


class UazapiErro(RuntimeError):
    pass


def config() -> dict:
    return {
        "URL": os.environ.get("UAZAPI_URL", "").strip().rstrip("/"),
        "TOKEN": os.environ.get("UAZAPI_TOKEN", "").strip(),
    }


def problemas(c: dict | None = None) -> list[str]:
    c = c or config()
    erros = []
    if not re.fullmatch(r"https://[A-Za-z0-9.\-]+(:\d+)?", c["URL"]):
        erros.append("UAZAPI_URL invalida (ex.: https://SEU-SUBDOMINIO.uazapi.com, sem barra no final)")
    if len(c["TOKEN"]) < 10:
        erros.append("UAZAPI_TOKEN vazio (token da INSTANCIA)")
    return erros


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):  # nunca repassar o token para outro endereco
        return None


def _abrir(req, timeout):
    return urllib.request.build_opener(_SemRedirecionar()).open(req, timeout=timeout)


def status(c: dict | None = None) -> str:
    c = c or config()
    req = urllib.request.Request(c["URL"] + "/instance/status", headers={"token": c["TOKEN"]})
    with _abrir(req, 20) as r:
        data = json.loads(r.read(65536) or b"{}")
    inst = data.get("instance") if isinstance(data.get("instance"), dict) else data
    return str(inst.get("status") or data.get("status") or "desconhecido")


def numero_valido(numero: str) -> bool:
    return bool(re.fullmatch(r"[1-9]\d{7,14}", numero or ""))


def enviar_texto(numero: str, texto: str, c: dict | None = None) -> str:
    """Envia texto. Devolve o id da mensagem (ou 'aceito' se a resposta nao trouxer id)."""
    c = c or config()
    if not numero_valido(numero):
        raise UazapiErro("NUMERO_INVALIDO")
    corpo = json.dumps({"number": numero, "text": texto}).encode("utf-8")
    req = urllib.request.Request(c["URL"] + "/send/text", data=corpo, method="POST",
                                 headers={"token": c["TOKEN"], "Content-Type": "application/json"})
    with _abrir(req, 30) as r:
        data = json.loads(r.read(65536) or b"{}")
    mid = data.get("messageid") or data.get("id") or (data.get("message") or {}).get("messageid")
    if data.get("error"):
        raise UazapiErro("RECUSADO_PELA_UAZAPI")
    return str(mid or "aceito")


def _ts(valor) -> float:
    """messageTimestamp pode vir em segundos ou milissegundos."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return 0.0
    return v / 1000 if v > 1e11 else v


def buscar_mensagens(numero: str, limite: int = 10, c: dict | None = None) -> list[dict]:
    """Ultimas mensagens da conversa com `numero` (normalizadas + 'ts' em segundos)."""
    c = c or config()
    if not numero_valido(numero):
        raise UazapiErro("NUMERO_INVALIDO")
    corpo = json.dumps({"chatid": f"{numero}@s.whatsapp.net", "limit": int(limite)}).encode("utf-8")
    req = urllib.request.Request(c["URL"] + "/message/find", data=corpo, method="POST",
                                 headers={"token": c["TOKEN"], "Content-Type": "application/json"})
    with _abrir(req, 20) as r:
        data = json.loads(r.read(2_000_000) or b"{}")
    itens = data.get("messages") if isinstance(data, dict) else data
    if isinstance(itens, dict):
        itens = itens.get("messages") or []
    saida = []
    for m in itens or []:
        if not isinstance(m, dict):
            continue
        n = extrair_mensagem({"EventType": "messages", "message": m})
        if n and n["id"]:
            n["ts"] = _ts(m.get("messageTimestamp") or m.get("timestamp"))
            saida.append(n)
    return saida


def eventos(c: dict | None = None, tipos: str = "messages", parar=lambda: False):
    """Gera os eventos (dict) recebidos pelo SSE; reconecta sozinho com espera crescente."""
    c = c or config()
    espera = 2
    while not parar():
        url = c["URL"] + "/sse?" + urllib.parse.urlencode({"token": c["TOKEN"], "events": tipos})
        try:
            req = urllib.request.Request(url, headers={"Accept": "text/event-stream"})
            with _abrir(req, 90) as r:
                espera = 2
                buffer = []
                for raw in r:
                    if parar():
                        return
                    linha = raw.decode("utf-8", "replace").rstrip("\r\n")
                    if linha.startswith("data:"):
                        buffer.append(linha[5:].lstrip())
                    elif linha == "" and buffer:
                        texto = "\n".join(buffer)
                        buffer = []
                        try:
                            yield json.loads(texto)
                        except ValueError:
                            continue
        except TimeoutError:
            # conexao ociosa (sem mensagens): normal. Reconecta em silencio; a busca de
            # reserva do atendente cobre qualquer mensagem nesse intervalo.
            espera = 2
            time.sleep(1)
            continue
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            # queda de rede / timeout / 401: reconecta. So o TIPO/codigo e mostrado (a URL tem o token).
            codigo = getattr(exc, "code", "")
            print(f"SSE UazAPI: conexao perdida ({type(exc).__name__} {codigo}); "
                  f"nova tentativa em {espera}s", file=sys.stderr, flush=True)
        time.sleep(espera)
        espera = min(espera * 2, 60)


def tipo_mensagem(msg: dict) -> str:
    """texto | audio | imagem | documento | outro (video, figurinha...) | ignorar (reacao, edicao, apagada)."""
    conteudo = msg.get("content") if isinstance(msg.get("content"), dict) else {}
    sinais = " ".join(str(x).lower() for x in (msg.get("messageType"), msg.get("mediaType"),
                                                 conteudo.get("mimetype"), conteudo.get("mimeType")) if x)
    if any(k in sinais for k in ("reaction", "protocol", "edited", "revoke", "pollupdate", "keepinchat")):
        return "ignorar"
    if "audio" in sinais or "ptt" in sinais:
        return "audio"
    if "image" in sinais and "sticker" not in sinais:
        return "imagem"
    if "document" in sinais or "pdf" in sinais:
        return "documento"
    if any(k in sinais for k in ("video", "sticker", "location", "contact", "poll")):
        return "outro"
    return "texto"


def baixar_midia(ids, generate_mp3: bool = True, c: dict | None = None) -> tuple[bytes, str]:
    """Baixa a midia de uma mensagem recebida (POST /message/download). Tenta cada id
    (messageid e id da API). Devolve (bytes, mimetype)."""
    import base64
    c = c or config()
    ultimo = None
    for mid in [i for i in ids if i]:
        corpo = json.dumps({"id": mid, "return_base64": True, "generate_mp3": generate_mp3}).encode("utf-8")
        req = urllib.request.Request(c["URL"] + "/message/download", data=corpo, method="POST",
                                     headers={"token": c["TOKEN"], "Content-Type": "application/json"})
        try:
            with _abrir(req, 60) as r:
                data = json.loads(r.read(40_000_000) or b"{}")
        except urllib.error.HTTPError as exc:
            ultimo = exc
            if exc.code in (400, 404):
                continue
            raise
        mime = str(data.get("mimetype") or "")
        if data.get("base64Data"):
            return base64.b64decode(data["base64Data"]), mime
        url = str(data.get("fileURL") or "")
        if url.startswith("https://"):   # link publico temporario (sem token)
            with _abrir(urllib.request.Request(url), 60) as r:
                return r.read(40_000_000), mime
        ultimo = UazapiErro("MIDIA_SEM_CONTEUDO")
    raise UazapiErro(f"MIDIA_INDISPONIVEL ({type(ultimo).__name__ if ultimo else 'sem id'})")


def enviar_audio(numero: str, dados: bytes, mimetype: str = "audio/ogg; codecs=opus",
                 c: dict | None = None) -> str:
    """Envia nota de voz (POST /send/media, type=ptt)."""
    import base64
    c = c or config()
    if not numero_valido(numero):
        raise UazapiErro("NUMERO_INVALIDO")
    corpo = json.dumps({"number": numero, "type": "ptt", "file": base64.b64encode(dados).decode("ascii"),
                        "mimetype": mimetype}).encode("utf-8")
    req = urllib.request.Request(c["URL"] + "/send/media", data=corpo, method="POST",
                                 headers={"token": c["TOKEN"], "Content-Type": "application/json"})
    with _abrir(req, 90) as r:
        data = json.loads(r.read(65536) or b"{}")
    if data.get("error"):
        raise UazapiErro("RECUSADO_PELA_UAZAPI")
    return str(data.get("messageid") or data.get("id") or "aceito")


def extrair_mensagem(evento: dict) -> dict | None:
    """Normaliza um evento 'messages' (formato do webhook/SSE da UazAPI)."""
    if not isinstance(evento, dict):
        return None
    msg = evento.get("message")
    if not isinstance(msg, dict) and isinstance(evento.get("data"), dict):
        msg = evento["data"].get("message", evento["data"])
    if not isinstance(msg, dict):
        return None
    tipo_evento = str(evento.get("EventType") or evento.get("type") or "messages")
    if tipo_evento != "messages":
        return None
    chat = str(msg.get("chatid") or "")
    remetente = str(msg.get("sender") or chat)
    def _num(jid: str) -> str:   # "5541...:12@s.whatsapp.net" -> "5541..." (descarta o aparelho)
        return re.sub(r"\D", "", jid.split("@")[0].split(":")[0]) if jid.endswith("@s.whatsapp.net") else ""
    numero = _num(remetente) or _num(chat)   # @lid / @g.us -> "" (nao autorizado)
    return {
        "id": str(msg.get("messageid") or msg.get("id") or ""),
        "id_api": str(msg.get("id") or ""),
        "tipo": tipo_mensagem(msg),
        "numero": numero,
        "texto": str(msg.get("text") or ""),
        "de_mim": bool(msg.get("fromMe")),
        "grupo": bool(msg.get("isGroup")) or chat.endswith("@g.us"),
        "pela_api": bool(msg.get("wasSentByApi")),
    }
