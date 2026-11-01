"""Audio do atendente: transcricao (audio -> texto) e resposta em VOZ (texto -> audio).

Dois provedores, escolhidos no .env:
  ElevenLabs (voz natural + Scribe; o audio vai para a ElevenLabs) - scripts/configurar_elevenlabs.py
  Local      (faster-whisper no computador + voz pt-BR do Windows; o audio nao sai daqui)

Instalacao (uma vez, na pasta do projeto):
  .\\.venv\\Scripts\\python.exe -m pip install faster-whisper
Na 1a transcricao o modelo e baixado (WA_WHISPER_MODELO, padrao "small", ~500 MB).

Variaveis (.env):
  WA_WHISPER_MODELO=small     tiny | base | small | medium (maior = melhor e mais lento)
  WA_RESPOSTA_VOZ=true        responde audio com audio (alem do texto)
  VOZ_PROVEDOR=elevenlabs | windows          (padrao: elevenlabs se houver chave)
  TRANSCRICAO_PROVEDOR=elevenlabs | local    (padrao: elevenlabs se houver chave)
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading

MAX_FALA = 700             # caracteres falados; o restante fica so no texto
_modelo = None
_trava = threading.Lock()
_pronto = threading.Event()


class VozErro(RuntimeError):
    pass


def modelo_nome() -> str:
    return os.environ.get("WA_WHISPER_MODELO", "").strip() or "small"


def resposta_em_voz() -> bool:
    return os.environ.get("WA_RESPOSTA_VOZ", "true").strip().lower() == "true"


def _provedor(var: str, local: str) -> str:
    from integrations import elevenlabs
    escolha = os.environ.get(var, "").strip().lower()
    if escolha in ("elevenlabs", local):
        return escolha
    return "elevenlabs" if elevenlabs.chave_ok() else local


def provedor_transcricao() -> str:
    return _provedor("TRANSCRICAO_PROVEDOR", "local")


def provedor_voz() -> str:
    return _provedor("VOZ_PROVEDOR", "windows")


# --- transcricao (audio -> texto) -------------------------------------------------
def whisper_instalado() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _groq_ok() -> bool:
    k = os.environ.get("GROQ_API_KEY", "").strip()
    return len(k) >= 20 and " " not in k


def transcrever_groq(dados: bytes, nome: str = "audio.mp3", mime: str = "audio/mpeg") -> str:
    """Reserva: Whisper da Groq (gratuito, nuvem)."""
    import json as _json
    import urllib.request
    import uuid
    limite = "----robo" + uuid.uuid4().hex
    partes = [f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
              for k, v in (("model", os.environ.get("GROQ_MODELO_STT", "") or "whisper-large-v3-turbo"),
                           ("language", "pt"), ("response_format", "json"))]
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="file"; filename="{nome}"\r\n'
                  f"Content-Type: {mime}\r\n\r\n".encode() + dados + b"\r\n")
    partes.append(f"--{limite}--\r\n".encode())
    req = urllib.request.Request("https://api.groq.com/openai/v1/audio/transcriptions", data=b"".join(partes),
                                 method="POST", headers={"Authorization": "Bearer " + os.environ["GROQ_API_KEY"].strip(),
                                                         "Content-Type": f"multipart/form-data; boundary={limite}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            texto = str(_json.loads(r.read() or b"{}").get("text") or "").strip()
    except Exception as exc:
        raise VozErro(f"GROQ_STT_FALHOU ({type(exc).__name__})") from None
    if not texto:
        raise VozErro("AUDIO_SEM_FALA")
    return texto


def transcricao_disponivel() -> bool:
    if provedor_transcricao() == "elevenlabs":
        from integrations import elevenlabs
        if elevenlabs.chave_ok():
            return True
    return whisper_instalado() or _groq_ok()


def descricao_transcricao() -> str:
    if provedor_transcricao() == "elevenlabs":
        from integrations import elevenlabs
        return f"ElevenLabs ({elevenlabs.config()['MODELO_STT']})"
    return f"local (Whisper '{modelo_nome()}')"


def _carregar():
    global _modelo
    with _trava:
        if _modelo is None:
            from faster_whisper import WhisperModel
            _modelo = WhisperModel(modelo_nome(), device="cpu", compute_type="int8")
            _pronto.set()
    return _modelo


def transcrever(dados: bytes, sufixo: str = ".mp3") -> str:
    if not dados:
        raise VozErro("AUDIO_VAZIO")
    mime = "audio/mpeg" if sufixo == ".mp3" else "audio/ogg"
    erros = []
    if provedor_transcricao() == "elevenlabs":
        from integrations import elevenlabs
        try:
            return elevenlabs.transcrever(dados, "audio" + sufixo, mime)
        except Exception as exc:              # sem credito/fora do ar: tenta a reserva
            erros.append(exc)
    if _groq_ok():
        try:
            return transcrever_groq(dados, "audio" + sufixo, mime)
        except VozErro as exc:
            if "AUDIO_SEM_FALA" in str(exc):
                raise
            erros.append(exc)
    if not whisper_instalado():
        raise VozErro("TRANSCRICAO_INDISPONIVEL") if not erros else erros[-1]
    if not _pronto.is_set() and _trava.locked():   # 1o download do modelo em andamento: nao trava o robo
        raise VozErro("MODELO_CARREGANDO")
    modelo = _carregar()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        arq = Path(d) / ("audio" + sufixo)
        arq.write_bytes(dados)
        segmentos, _info = modelo.transcribe(str(arq), language="pt", vad_filter=True, beam_size=5)
        texto = " ".join(s.text.strip() for s in segmentos).strip()
    if not texto:
        raise VozErro("AUDIO_SEM_FALA")
    return texto


# --- voz (texto -> audio) ---------------------------------------------------------
_PS = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'pt-BR' } | Select-Object -First 1
if (-not $v) { Write-Output 'SEM_VOZ_PTBR'; exit 3 }
$s.SelectVoice($v.VoiceInfo.Name)
if ($env:TTS_LISTAR -eq '1') { Write-Output $v.VoiceInfo.Name; exit 0 }
$s.Rate = 1
$s.SetOutputToWaveFile($env:TTS_WAV)
$s.Speak([IO.File]::ReadAllText($env:TTS_TXT, [Text.Encoding]::UTF8))
$s.Dispose()
"""


def _powershell(env_extra: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ, **env_extra)
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-Command", _PS], env=env, capture_output=True, text=True, timeout=120,
                          encoding="utf-8", errors="replace",
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def voz_disponivel() -> str:
    """Descricao da voz que sera usada ('' se nenhuma)."""
    if provedor_voz() == "elevenlabs":
        from integrations import elevenlabs
        c = elevenlabs.config()
        return f"ElevenLabs (voz {c['VOZ'][:6]}..., {c['MODELO_VOZ']})" if elevenlabs.chave_ok(c) and c["VOZ"] else ""
    return voz_windows()


def voz_windows() -> str:
    """Nome da voz pt-BR instalada no Windows ('' se nao houver)."""
    try:
        r = _powershell({"TTS_LISTAR": "1"})
    except Exception:
        return ""
    nome = (r.stdout or "").strip().splitlines()
    return nome[-1] if r.returncode == 0 and nome and nome[-1] != "SEM_VOZ_PTBR" else ""


def texto_para_fala(texto: str) -> str:
    """Limpa o texto do WhatsApp para soar natural e corta no limite (frase inteira)."""
    t = re.sub(r"[*_~`•]", " ", texto or "")
    t = re.sub(r"[\U0001F000-\U0001FAFF☀-➿]", " ", t)          # emojis
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\s*\n\s*", ". ", t).strip(" .")
    t = re.sub(r"\.(\s*\.)+", ".", t)
    if len(t) > MAX_FALA:
        corte = t[:MAX_FALA]
        p = max(corte.rfind(". "), corte.rfind("; "))
        t = (corte[:p + 1] if p > 200 else corte) + " O restante está na mensagem de texto."
    return t


def _para_ogg(origem: Path, ogg: Path) -> None:
    import av
    with av.open(str(origem)) as entrada, av.open(str(ogg), "w", format="ogg") as saida:
        try:
            fluxo = saida.add_stream("libopus", rate=48000, layout="mono")
        except TypeError:                      # versoes antigas do PyAV
            fluxo = saida.add_stream("libopus", rate=48000)
        conv = av.AudioResampler(format="s16", layout="mono", rate=48000)
        for quadro in entrada.decode(audio=0):
            for q in conv.resample(quadro):
                for pacote in fluxo.encode(q):
                    saida.mux(pacote)
        for q in conv.resample(None) or []:
            for pacote in fluxo.encode(q):
                saida.mux(pacote)
        for pacote in fluxo.encode(None):
            saida.mux(pacote)


def sintetizar(texto: str) -> tuple[bytes, str]:
    """Texto -> (bytes OGG/Opus, mimetype) pronto para nota de voz do WhatsApp."""
    fala = texto_para_fala(texto)
    if not fala:
        raise VozErro("TEXTO_VAZIO")
    if provedor_voz() == "elevenlabs":
        from integrations import elevenlabs
        try:
            mp3 = elevenlabs.falar(fala)
        except Exception:
            # ElevenLabs sem credito/permissao/fora do ar: usa a voz do Windows, se houver
            if voz_windows():
                return _sintetizar_windows(fala)
            raise
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            origem, ogg = Path(d) / "fala.mp3", Path(d) / "fala.ogg"
            origem.write_bytes(mp3)
            try:                                   # nota de voz nativa (OGG/Opus) se o PyAV existir
                _para_ogg(origem, ogg)
                if ogg.stat().st_size > 0:
                    return ogg.read_bytes(), "audio/ogg; codecs=opus"
            except Exception:
                pass
        return mp3, "audio/mpeg"
    return _sintetizar_windows(fala)


def _sintetizar_windows(fala: str) -> tuple[bytes, str]:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
        txt, wav, ogg = Path(d) / "fala.txt", Path(d) / "fala.wav", Path(d) / "fala.ogg"
        txt.write_text(fala, encoding="utf-8")
        r = _powershell({"TTS_TXT": str(txt), "TTS_WAV": str(wav)})
        if r.returncode != 0 or not wav.exists():
            raise VozErro("SEM_VOZ_PTBR" if "SEM_VOZ_PTBR" in (r.stdout or "") else "FALHA_TTS")
        try:
            _para_ogg(wav, ogg)
            if ogg.stat().st_size > 0:
                return ogg.read_bytes(), "audio/ogg; codecs=opus"
        except Exception:
            pass
        return wav.read_bytes(), "audio/wav"   # sem conversor: a UazAPI recebe o WAV
