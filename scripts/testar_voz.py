"""Confere a ElevenLabs com a chave do .env (a chave NUNCA aparece na tela).
Mostra: creditos usados/limite (se a chave tiver permissao) e se a voz consegue falar.
Uso: dois cliques em TESTAR_VOZ.bat
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

from integrations import elevenlabs  # noqa: E402

EXPLICA = {
    "quota_exceeded": "SEM CREDITOS suficientes no plano (ou limite da chave atingido).",
    "missing_permissions": "a CHAVE nao tem a permissao necessaria (edite a chave em Developers > API Keys).",
    "invalid_api_key": "chave invalida ou apagada.",
    "detected_unusual_activity": "a ElevenLabs bloqueou o plano gratuito por atividade incomum (VPN/varias contas).",
}


def _motivo(exc) -> str:
    t = str(exc)
    for k, v in EXPLICA.items():
        if k in t:
            return f"{t} -> {v}"
    return t


def main() -> int:
    c = elevenlabs.config()
    if not elevenlabs.chave_ok(c):
        print("ELEVENLABS_API_KEY vazia no .env. Rode CONFIGURAR_ELEVENLABS.bat.")
        return 2
    print("1) Creditos da conta")
    try:
        req = urllib.request.Request(elevenlabs.API + "/v1/user/subscription", headers={"xi-api-key": c["CHAVE"]})
        with elevenlabs._abrir(req, 20) as r:
            s = json.loads(r.read())
        usado, limite = s.get("character_count", 0), s.get("character_limit", 0)
        reset = s.get("next_character_count_reset_unix")
        print(f"   Plano: {s.get('tier', '?')}  |  usados {usado:,} de {limite:,}  |  restam {max(0, limite - usado):,}")
        if reset:
            print(f"   Renovacao: {datetime.fromtimestamp(reset):%d/%m/%Y %H:%M}")
    except Exception as exc:
        print(f"   Nao consegui ler ({_motivo(exc)})")
        print("   (normal se a chave nao tiver a permissao 'User'; veja os creditos no site: elevenlabs.io/app/subscription)")
    print("2) Teste de voz (gasta ~20 caracteres)")
    try:
        mp3 = elevenlabs.falar("Teste de voz do assistente.", c)
        print(f"   VOZ OK ({len(mp3):,} bytes). RESULTADO=VOZ_OK")
        return 0
    except Exception as exc:
        print(f"   FALHOU: {_motivo(exc)}")
        print("   RESULTADO=VOZ_FALHOU")
        return 3


if __name__ == "__main__":
    code = main()
    try:
        input("\nEnter para fechar...")
    except EOFError:
        pass
    raise SystemExit(code)
