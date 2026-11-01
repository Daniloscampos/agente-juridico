"""Teste da conexao com a UazAPI (numero do escritorio).

  U1 configuracao   UAZAPI_URL e UAZAPI_TOKEN no .env
  U2 instancia      /instance/status = connected
  U3 destinatarios  numeros internos cadastrados (mascarados)
  U4 envio          SOMENTE com --enviar: manda "teste" para os numeros cadastrados

Uso:
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_uazapi.py
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_uazapi.py --enviar
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


def ok(cod, nome, passou, detalhe=""):
    print(f"[{'OK   ' if passou else 'FALHA'}] {cod} {nome}" + (f" - {detalhe}" if detalhe else ""))
    return passou


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enviar", action="store_true")
    args = ap.parse_args(argv)

    from core import control
    from core.config import settings
    from core.policy import Blocked, enforce
    from core.store import Store
    from integrations import uazapi
    from integrations.whatsapp_integra import cfg, destinatarios

    erros = uazapi.problemas()
    if not ok("U1", "configuracao", not erros, "; ".join(erros) or "UAZAPI_URL e UAZAPI_TOKEN preenchidos"):
        print("RESULTADO_FINAL=PENDENTE_CONFIGURACAO")
        return 1
    try:
        estado = uazapi.status()
    except Exception as exc:
        estado = f"erro {type(exc).__name__}"
    if not ok("U2", "instancia UazAPI", estado == "connected", estado):
        print("RESULTADO_FINAL=NUMERO_DESCONECTADO (conecte pelo QR Code no painel da UazAPI)")
        return 1
    store = Store(settings.AGENT_DB)
    alvos = destinatarios(store, cfg())
    ok("U3", "destinatarios internos", bool(alvos), ", ".join(f"{n} (***{p[-4:]})" for n, p in alvos.items()) or
       "nenhum - scripts\\manage_whatsapp.py add USUARIO --phone 55DDDNUMERO --internal-consent")
    if not args.enviar:
        print("RESULTADO_FINAL=" + ("CONEXAO_OK" if alvos else "PENDENTE_DESTINATARIO"))
        return 0
    if control.is_paused():
        print("RESULTADO_FINAL=BLOQUEADO (.paused)")
        return 1
    try:
        enforce(store, "aviso_interno")
    except Blocked as exc:
        print(f"RESULTADO_FINAL=BLOQUEADO ({exc})")
        return 1
    falhas = 0
    for nome, fone in alvos.items():
        try:
            uazapi.enviar_texto(fone, f"Robô Peres & Javarotti: teste de conexão ({datetime.now():%d/%m/%Y %H:%M}). "
                                      "Responda 'ajuda' quando o atendente estiver ligado.")
            ok("U4", f"envio para {nome}", True)
        except Exception as exc:
            falhas += 1
            ok("U4", f"envio para {nome}", False, type(exc).__name__)
    store.event(action="teste_uazapi", actor="robo", result="confirmado" if not falhas else "parcial")
    print("RESULTADO_FINAL=" + ("ENVIO_ACEITO" if not falhas else "ENVIO_COM_FALHA") +
          " - confira no celular")
    return 0 if not falhas else 1


if __name__ == "__main__":
    raise SystemExit(main())
