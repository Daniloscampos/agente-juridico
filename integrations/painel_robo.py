"""Resumo do robo de WhatsApp para o painel (somente leitura; sem conteudo de mensagens nem chaves)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

HEARTBEAT = Path("var/atendente.heartbeat")
ATIVO_SEGUNDOS = 60


def _env() -> dict:
    """Le o .env sem alterar o processo do painel (nunca devolve valores secretos)."""
    try:
        from dotenv import dotenv_values
        valores = {k: (v or "") for k, v in dotenv_values(".env").items()}
    except Exception:
        valores = {}
    return {**valores, **{k: v for k, v in os.environ.items() if k.startswith(("WA_", "UAZAPI_", "VOZ_", "TRANSC"))}}


def _sim(v) -> bool:
    return str(v or "").strip().lower() == "true"


def _ia_ligada(env: dict) -> bool:
    if not _sim(env.get("WA_IA_ENABLED")):
        return False
    lista = [x.strip().lower() for x in (env.get("IA_PROVEDORES") or env.get("IA_PROVEDOR") or "").split(",")
             if x.strip()]
    return any({"claude": bool(env.get("ANTHROPIC_API_KEY")), "groq": bool(env.get("GROQ_API_KEY")),
                "ollama": True}.get(p, False) for p in lista) or bool(env.get("ANTHROPIC_API_KEY"))


def _ia_estado() -> list:
    try:
        from integrations.ia_orquestrador import ler_estado
        return ler_estado().get("provedores", [])
    except Exception:
        return []


def resumo(store) -> dict:
    env = _env()
    agora = datetime.now(timezone.utc)
    inicio_dia = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

    # robo ligado? (o atendente grava um sinal a cada poucos segundos)
    try:
        idade = time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        idade = None
    robo = {"ativo": idade is not None and idade < ATIVO_SEGUNDOS,
            "ultimo_sinal_seg": None if idade is None else int(idade)}

    # pessoas autorizadas (mesma regra do robo)
    pessoas = {}
    try:
        from integrations.whatsapp import recipients
        caminho = env.get("WA_RECIPIENTS_FILE") or "var/whatsapp-recipients.json"
        pessoas = recipients(store, {"RECIPIENTS_FILE": caminho})
    except Exception:
        pass
    por_fone = {f: u for u, f in pessoas.items()}

    with store.db() as db:
        tabelas = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        atend = []
        if "whatsapp_inbox" in tabelas:
            atend = [dict(zip(("recebido", "numero", "comando", "resultado"), r)) for r in db.execute(
                "SELECT recebido, numero, comando, resultado FROM whatsapp_inbox ORDER BY recebido DESC LIMIT 400")]
        avisos = {}
        if "whatsapp_integra_outbox" in tabelas:
            avisos = dict(db.execute("SELECT state, COUNT(*) FROM whatsapp_integra_outbox GROUP BY state").fetchall())
        pubs = {"total": 0, "hoje": 0, "sem_vinculo": 0, "ultima_leitura": None}
        if "integra_publicacoes" in tabelas:
            pubs["total"] = db.execute("SELECT COUNT(*) FROM integra_publicacoes").fetchone()[0]
            pubs["sem_vinculo"] = db.execute(
                "SELECT COUNT(*) FROM integra_publicacoes WHERE status_vinculo='vinculo_pendente'").fetchone()[0]
            pubs["hoje"] = db.execute("SELECT COUNT(*) FROM integra_publicacoes WHERE primeira_leitura>=?",
                                      (inicio_dia.isoformat(),)).fetchone()[0]
            pubs["ultima_leitura"] = db.execute("SELECT MAX(ultima_leitura) FROM integra_publicacoes").fetchone()[0]

    def _quando(iso):
        try:
            return datetime.fromisoformat(iso)
        except (TypeError, ValueError):
            return None

    hoje = [a for a in atend if (_quando(a["recebido"]) or agora) >= inicio_dia]
    respondidos = [a for a in hoje if a["resultado"].startswith("respondido")]
    ignorados = [a for a in hoje if a["comando"] == "ignorado"]
    falhas = [a for a in hoje if any(k in a["resultado"] for k in ("erro", "falhou", "bloqueado"))]
    ultimos = []
    for a in [x for x in atend if x["comando"] != "ignorado" or x["resultado"] == "nao_autorizado"][:15]:
        quem = por_fone.get(a["numero"]) or ("não cadastrado ***" + a["numero"][-4:] if a["numero"][-4:].isdigit()
                                             else "não cadastrado")
        ultimos.append({"quando": a["recebido"], "pessoa": quem, "pedido": a["comando"], "resultado": a["resultado"]})

    return {
        "robo": robo,
        "config": {
            "provedor": env.get("WA_PROVIDER") or "uazapi",
            "atendente": _sim(env.get("WA_ATENDENTE_ENABLED")),
            "aviso_automatico": _sim(env.get("WA_INTEGRA_ENABLED")),
            "whatsapp_configurado": bool(env.get("UAZAPI_URL")) and bool(env.get("UAZAPI_TOKEN")),
            "ia": _ia_ligada(env),
            "ia_provedor": (env.get("IA_PROVEDOR") or "claude").lower(),
            "ia_estado": _ia_estado(),
            "voz": (env.get("VOZ_PROVEDOR") or ("elevenlabs" if env.get("ELEVENLABS_API_KEY") else "windows")),
            "resposta_em_voz": _sim(env.get("WA_RESPOSTA_VOZ", "true")),
        },
        "pessoas": sorted(pessoas),
        "hoje": {"pedidos": len(hoje) - len(ignorados), "respondidos": len(respondidos),
                 "ignorados": len(ignorados), "falhas": len(falhas)},
        "ultimos": ultimos,
        "avisos": avisos,
        "publicacoes": pubs,
        "nota": "Sem conteúdo das mensagens. Horários de registro em UTC convertidos pelo navegador.",
    }


def batimento() -> None:
    """Chamado pelo atendente em funcionamento: atualiza o sinal de vida."""
    try:
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except OSError:
        pass


if __name__ == "__main__":   # diagnostico rapido no terminal
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from core.store import Store
    print(json.dumps(resumo(Store(os.environ.get("AGENT_DB", "var/operational.sqlite"))), indent=2,
                     ensure_ascii=False, default=str))
