"""Teste do aviso de WhatsApp das publicacoes do INTEGRA.

Etapas:
  W1 configuracao   WA_INTEGRA_ENABLED, WA_TOKEN, WA_PHONE_NUMBER_ID, WA_API_VERSION, template
  W2 destinatarios  cadastrados com scripts/manage_whatsapp.py (numeros mascarados na tela)
  W3 permissao      acao "aviso_interno" liberada (pausa / modo erro / revisao do painel)
  W4 previa         monta a mensagem com as publicacoes ja gravadas no banco (nao envia)
  W5 envio          SOMENTE com --enviar: envia UMA mensagem de teste a cada destinatario

Uso:
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_whatsapp_integra.py            # W1-W4, nada e enviado
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_whatsapp_integra.py --enviar   # inclui W5
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")  # o dispatcher original nao le .env; aqui o teste le para facilitar


def ok(cod, nome, passou, detalhe=""):
    print(f"[{'OK   ' if passou else 'FALHA'}] {cod} {nome}" + (f" - {detalhe}" if detalhe else ""))
    return passou


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enviar", action="store_true", help="Envia uma mensagem de teste a cada destinatario")
    args = ap.parse_args(argv)

    from core.config import settings
    from core.policy import Blocked, enforce
    from core.store import Store
    from integrations import whatsapp_integra as wi

    store = Store(settings.AGENT_DB)
    c = wi.cfg()

    erros = wi.problemas_config(c)
    w1 = ok("W1", "configuracao", not erros, "; ".join(erros) or f"template={c['TEMPLATE_PUBLICACOES']}")

    try:
        alvos = wi.destinatarios(store, c)
    except Exception as exc:
        alvos = {}
        print(f"        erro ao ler destinatarios: {type(exc).__name__}")
    mascarados = [f"{n} (***{p[-4:]})" for n, p in alvos.items()]
    w2 = ok("W2", "destinatarios internos", bool(alvos), ", ".join(mascarados) or
            "nenhum - cadastre com scripts\\manage_whatsapp.py add USUARIO --phone 55DDDNUMERO --internal-consent")

    try:
        from core import control
        if control.is_paused():  # pausa dupla: arquivo .paused alem do painel
            raise Blocked("AGENTE_PAUSADO_ARQUIVO_.paused")
        enforce(store, wi.ACAO)
        w3 = ok("W3", "permissao aviso_interno", True, "liberada")
    except Blocked as exc:
        w3 = ok("W3", "permissao aviso_interno", False, f"{exc} - retome no painel")

    wi.preparar(store)
    with store.db() as db:
        try:
            linhas = db.execute("SELECT payload FROM integra_publicacoes ORDER BY primeira_leitura DESC LIMIT 20").fetchall()
        except Exception:
            linhas = []
    pubs = [json.loads(r[0]) for r in linhas]
    p1, p2, p3 = wi.montar_mensagem(pubs, {"lidas": len(pubs)}, c["PANEL_URL"], c["INCLUIR_PARTES"])
    ok("W4", "previa da mensagem", bool(pubs), f"{len(pubs)} publicacao(oes) no banco")
    print("\n--- PREVIA (como chegara no WhatsApp) ---")
    print(f"{{{{1}}}} {p1}\n{{{{2}}}} {p2}\n{{{{3}}}} {p3}")
    print("--- fim da previa ---\n")

    if not args.enviar:
        print("RESULTADO_FINAL=" + ("PRONTO_PARA_ENVIO" if (w1 and w2 and w3 and pubs) else "PENDENTE_CONFIGURACAO"))
        print("Nada foi enviado. Para enviar o teste: acrescente --enviar")
        return 0
    if not (w1 and w2 and w3 and pubs):
        print("RESULTADO_FINAL=ENVIO_NAO_REALIZADO (corrija as falhas acima)")
        return 1

    lote = "teste-" + datetime.now().strftime("%Y%m%d%H%M%S")
    with store.db() as db:
        for nome in alvos:
            db.execute("INSERT OR IGNORE INTO whatsapp_integra_outbox(lote,username,state,created,p1,p2,p3) "
                       "VALUES(?,?,'pendente',?,?,?,?)", (lote, nome, datetime.now().isoformat(), p1, p2, p3))
    res = wi.enviar_pendentes(store)
    with store.db() as db:  # confere so o lote de teste (ignora sobras antigas da fila)
        aceitos = db.execute("SELECT COUNT(*) FROM whatsapp_integra_outbox WHERE lote=? AND state='aceito_api'",
                             (lote,)).fetchone()[0]
    passou = aceitos == len(alvos)
    ok("W5", "envio", passou, json.dumps(res, ensure_ascii=False))
    print("Obs.: 'aceito_api' = aceito pela Meta. Confirme no celular se a mensagem chegou.")
    print("RESULTADO_FINAL=" + ("ENVIO_ACEITO" if passou else "ENVIO_COM_FALHA"))
    return 0 if passou else 1


if __name__ == "__main__":
    raise SystemExit(main())
