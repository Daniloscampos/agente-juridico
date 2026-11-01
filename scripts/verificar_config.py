"""Mostra a configuracao do robo SEM revelar chaves/tokens (so 'preenchido' ou 'vazio').

Uso:  .\\.venv\\Scripts\\python.exe .\\scripts\\verificar_config.py
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
SEGREDOS = {"UAZAPI_TOKEN", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "INTEGRA_SENHA", "INTEGRA_PASSWORD",
            "WA_TOKEN", "DASH_SECRET", "SECRET_KEY"}
MOSTRAR = ["WA_PROVIDER", "WA_ATENDENTE_ENABLED", "WA_INTEGRA_ENABLED", "UAZAPI_URL", "UAZAPI_TOKEN",
           "WA_IA_ENABLED", "ANTHROPIC_API_KEY", "IA_MODELO", "VOZ_PROVEDOR", "TRANSCRICAO_PROVEDOR",
           "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "WA_RESPOSTA_VOZ", "WA_INCLUIR_PARTES"]

if not ENV.exists():
    raise SystemExit("Arquivo .env nao encontrado na pasta do robo.")
valores, contagem = {}, Counter()
for ln in ENV.read_text(encoding="utf-8", errors="replace").splitlines():
    m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=(.*)", ln)
    if m and not ln.lstrip().startswith("#"):
        chave, valor = m.group(1), m.group(2).strip().strip('"').strip("'")
        contagem[chave] += 1
        valores[chave] = valor          # python-dotenv usa o ULTIMO valor
for chave in MOSTRAR:
    v = valores.get(chave)
    if v is None:
        txt = "(ausente)"
    elif chave in SEGREDOS or "KEY" in chave or "TOKEN" in chave:
        txt = f"preenchido ({len(v)} caracteres)" if v else "VAZIO"
    elif chave == "ELEVENLABS_VOICE_ID":
        txt = (v[:6] + "...") if v else "VAZIO"
    else:
        txt = v or "VAZIO"
    aviso = f"   <- REPETIDA {contagem[chave]}x no .env" if contagem[chave] > 1 else ""
    print(f"{chave:<22} {txt}{aviso}")
rep = [k for k, n in contagem.items() if n > 1]
print("\nChaves repetidas: " + (", ".join(rep) if rep else "nenhuma"))
