"""Cliente minimo da ElevenLabs (voz natural e transcricao) - HTTP direto, sem SDK.

  POST /v1/text-to-speech/{voice_id}?output_format=mp3_44100_128   texto -> MP3
  POST /v1/speech-to-text  (multipart: model_id, file, language_code) audio -> texto
  GET  /v1/voices                                                    vozes da conta

Chave so no .env (ELEVENLABS_API_KEY), header xi-api-key; nunca impressa.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
import uuid

API = "https://api.elevenlabs.io"
MODELO_VOZ_PADRAO = "eleven_multilingual_v2"     # pt-BR, normaliza numeros
MODELO_STT_PADRAO = "scribe_v2"


class ElevenErro(RuntimeError):
    pass


def config() -> dict:
    return {
        "CHAVE": os.environ.get("ELEVENLABS_API_KEY", "").strip(),
        "VOZ": os.environ.get("ELEVENLABS_VOICE_ID", "").strip(),
        "MODELO_VOZ": os.environ.get("ELEVENLABS_MODELO_VOZ", "").strip() or MODELO_VOZ_PADRAO,
        "MODELO_STT": os.environ.get("ELEVENLABS_MODELO_STT", "").strip() or MODELO_STT_PADRAO,
    }


def chave_ok(c: dict | None = None) -> bool:
    c = c or config()
    return len(c["CHAVE"]) >= 20 and " " not in c["CHAVE"]


def _abrir(req, timeout):
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:    # so codigo/status (nunca a chave)
        try:
            det = json.loads(exc.read() or b"{}").get("detail")
            status = det.get("status", "") if isinstance(det, dict) else ""
        except Exception:
            status = ""
        raise ElevenErro(f"HTTP {exc.code} {status}".strip()) from None


def vozes(c: dict | None = None) -> list[dict]:
    c = c or config()
    req = urllib.request.Request(API + "/v1/voices", headers={"xi-api-key": c["CHAVE"]})
    with _abrir(req, 30) as r:
        data = json.loads(r.read() or b"{}")
    saida = []
    for v in data.get("voices") or []:
        rot = v.get("labels") or {}
        saida.append({"id": v.get("voice_id", ""), "nome": v.get("name", ""),
                      "info": ", ".join(str(x) for x in (rot.get("gender"), rot.get("accent"),
                                                         rot.get("language"), rot.get("age")) if x)})
    return [v for v in saida if v["id"]]


def falar(texto: str, c: dict | None = None) -> bytes:
    """Texto -> MP3 (bytes)."""
    c = c or config()
    if not c["VOZ"]:
        raise ElevenErro("ELEVENLABS_VOICE_ID vazio")
    corpo = json.dumps({"text": texto, "model_id": c["MODELO_VOZ"]}).encode("utf-8")
    req = urllib.request.Request(f"{API}/v1/text-to-speech/{c['VOZ']}?output_format=mp3_44100_128",
                                 data=corpo, method="POST",
                                 headers={"xi-api-key": c["CHAVE"], "Content-Type": "application/json",
                                          "Accept": "audio/mpeg"})
    with _abrir(req, 90) as r:
        dados = r.read()
    if not dados:
        raise ElevenErro("AUDIO_VAZIO")
    return dados


def transcrever(dados: bytes, nome: str = "audio.mp3", mime: str = "audio/mpeg", c: dict | None = None) -> str:
    """Audio -> texto (Scribe), portugues."""
    c = c or config()
    limite = "----robo" + uuid.uuid4().hex
    partes = []
    for campo, valor in (("model_id", c["MODELO_STT"]), ("language_code", "por"), ("tag_audio_events", "false")):
        partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{campo}"\r\n\r\n{valor}\r\n'.encode())
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nome}"\r\n'
                  f"Content-Type: {mime}\r\n\r\n".encode() + dados + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    req = urllib.request.Request(API + "/v1/speech-to-text", data=b"".join(partes), method="POST",
                                 headers={"xi-api-key": c["CHAVE"],
                                          "Content-Type": f"multipart/form-data; boundary={limite}"})
    with _abrir(req, 120) as r:
        data = json.loads(r.read() or b"{}")
    texto = str(data.get("text") or "").strip()
    if not texto:
        raise ElevenErro("AUDIO_SEM_FALA")
    return texto
