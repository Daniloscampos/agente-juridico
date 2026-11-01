"""Aviso por WhatsApp das publicacoes lidas no INTEGRA — somente equipe INTERNA.

Fluxo: executar_integra.py le e grava as publicacoes -> enfileirar() monta UMA mensagem
por lote de publicacoes novas/alteradas -> enviar_pendentes() envia pela WhatsApp Cloud
API oficial (template aprovado), a cada destinatario cadastrado.

Permissoes respeitadas (core/policy.py):
  * acao "aviso_interno" (AUTO) — bloqueada por pausa, modo erro ou regra de revisao;
  * nunca "enviar_cliente": so recebe quem esta no cadastro interno (scripts/manage_whatsapp.py),
    usuario ativo do painel, com consentimento registrado;
  * a mensagem so repete o que o robo leu na LISTAGEM (processo, vara/comarca, datas,
    contagens). Nao abre a publicacao, nao interpreta prazo e nao da orientacao juridica.

Seguranca de envio (mesmo padrao do dispatcher existente):
  * fila persistente; o mesmo lote nunca e enviado duas vezes ao mesmo numero;
  * intencao gravada ANTES da chamada de rede; timeout/erro 5xx = "reconciliar" (nao reenvia
    sozinho); erro 4xx = "recusado";
  * "aceito_api" significa aceito pela Meta, nao entregue/lido.

Variaveis de ambiente (alem das WA_* do dispatcher):
  WA_INTEGRA_ENABLED=true            liga este aviso (padrao: desligado)
  WA_TEMPLATE_PUBLICACOES=nome       template aprovado com 3 parametros no corpo
  WA_INCLUIR_PARTES=false            true = inclui cliente x parte adversa (decisao do escritorio)
"""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

from core.policy import Blocked, enforce
from core.store import now

ACAO = "aviso_interno"
EVENTO = "aviso_integra_publicacoes"
MAX_PARAM = 900          # limite seguro por parametro (corpo do template <= 1024)
CORPO_MAX = 1024         # corpo renderizado (texto fixo + parametros) aceito pela Meta
TEXTO_FIXO = 260         # reserva para o texto fixo do template (secao 3 da doc: ~230 caracteres)

SCHEMA = """
CREATE TABLE IF NOT EXISTS whatsapp_integra_outbox(
    lote TEXT NOT NULL, username TEXT NOT NULL, state TEXT NOT NULL,
    created TEXT NOT NULL, updated TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL DEFAULT '', p1 TEXT NOT NULL, p2 TEXT NOT NULL, p3 TEXT NOT NULL,
    PRIMARY KEY(lote, username));
"""


# ---------------------------------------------------------------- configuracao
def cfg() -> dict:
    from integrations.whatsapp import config
    c = config()
    c["INTEGRA_ENABLED"] = os.environ.get("WA_INTEGRA_ENABLED", "").strip().lower() == "true"
    c["TEMPLATE_PUBLICACOES"] = os.environ.get("WA_TEMPLATE_PUBLICACOES", "").strip()
    c["INCLUIR_PARTES"] = os.environ.get("WA_INCLUIR_PARTES", "").strip().lower() == "true"
    # meta = WhatsApp Cloud API oficial (template) | uazapi = numero conectado na UazAPI (texto livre)
    c["PROVIDER"] = os.environ.get("WA_PROVIDER", "meta").strip().lower()
    return c


def problemas_config(c: dict) -> list[str]:
    erros = []
    if not c["INTEGRA_ENABLED"]:
        erros.append("WA_INTEGRA_ENABLED diferente de true")
    if c.get("PROVIDER") == "uazapi":
        from integrations import uazapi
        return erros + uazapi.problemas()
    if c.get("PROVIDER") not in (None, "meta"):
        return erros + ["WA_PROVIDER deve ser meta ou uazapi"]
    if not c["TOKEN"]:
        erros.append("WA_TOKEN vazio")
    if not re.fullmatch(r"\d+", c["PHONE_NUMBER_ID"] or ""):
        erros.append("WA_PHONE_NUMBER_ID invalido")
    if not re.fullmatch(r"v\d+\.\d+", c["API_VERSION"] or ""):
        erros.append("WA_API_VERSION invalido (ex.: v21.0)")
    if not re.fullmatch(r"[a-z0-9_]+", c["TEMPLATE_PUBLICACOES"]):
        erros.append("WA_TEMPLATE_PUBLICACOES invalido")
    return erros


def destinatarios(store, c: dict) -> dict:
    """Somente usuarios internos cadastrados (mesma regra do dispatcher existente)."""
    from integrations.whatsapp import recipients
    return recipients(store, c)


# ---------------------------------------------------------------- mensagem
def _limpo(texto: str) -> str:
    # A Meta recusa parametros com quebra de linha, tab ou mais de 4 espacos seguidos.
    return re.sub(r"\s+", " ", str(texto or "")).strip()


def _cortar(texto: str, limite: int = MAX_PARAM) -> str:
    return texto if len(texto) <= limite else texto[: limite - 3].rstrip() + "..."


def montar_mensagem(publicacoes: list[dict], resumo: dict, painel: str, incluir_partes: bool = False):
    """Devolve (p1, p2, p3) para o template. publicacoes = itens de Publicacao.to_dict()."""
    hoje = datetime.now().strftime("%d/%m/%Y")
    pend = sum(1 for p in publicacoes if not p.get("processos"))
    p1 = (f"{len(publicacoes)} publicacao(oes) nova(s) em {hoje}; {pend} sem processo vinculado; "
          f"total listado no INTEGRA: {resumo.get('rodape_total', resumo.get('lidas', len(publicacoes)))}")
    itens = []
    for i, p in enumerate(publicacoes, 1):
        procs = p.get("processos") or []
        if procs:
            numeros = ", ".join(x["numero_cnj"] for x in procs)
        else:
            numeros = "SEM PROCESSO VINCULADO"
        partes = ""
        if incluir_partes and procs:
            partes = " (" + "; ".join(f"{x.get('cliente', '')} x {x.get('parte_adversa', '')}" for x in procs) + ")"
        # A listagem corta o nome do orgao ("20ª Câmara de Direit"); o title traz o nome completo.
        comarca = (p.get("orgao_comarca") or "").rsplit(" - ", 1)[-1] if " - " in (p.get("orgao_comarca") or "") else ""
        vara = " - ".join(x for x in (p.get("orgao") or p.get("orgao_comarca") or "orgao nao informado", comarca) if x)
        itens.append(f"{i}) {numeros} - {vara}"
                     f" - disp. {p.get('data_disponibilizacao') or '?'}{partes}")
    p1 = _cortar(_limpo(p1), 200)
    p3 = _cortar(_limpo(painel if painel.startswith("https://") else "painel interno do escritorio"), 200)
    # Soma total do corpo <= 1024: o que sobra do texto fixo, p1 e p3 vai para a lista (p2).
    limite_p2 = min(MAX_PARAM, CORPO_MAX - TEXTO_FIXO - len(p1) - len(p3)) - 40
    p2, usados = "", 0
    for item in (_limpo(x) for x in itens):
        candidato = (p2 + " | " if p2 else "") + item
        if len(candidato) > limite_p2:
            if not p2:  # item unico longo demais: corta o item em vez de omiti-lo
                p2, usados = _cortar(item, limite_p2), 1
            break
        p2, usados = candidato, usados + 1
    if usados < len(itens):
        p2 += f" | e mais {len(itens) - usados} no painel"
    return p1, _cortar(_limpo(p2 or "nenhuma")), p3


# ---------------------------------------------------------------- fila
def preparar(store) -> None:
    with store.db() as db:
        db.executescript(SCHEMA)


def enfileirar(store, codigos: list[str], resumo: dict) -> str | None:
    """Cria um lote para os codigos novos/alterados. Nada a avisar -> None."""
    if not codigos:
        return None
    c = cfg()
    preparar(store)
    lote = hashlib.sha256(("|".join(sorted(codigos))).encode()).hexdigest()[:24]
    with store.db() as db:
        pubs = []
        for cod in codigos:
            row = db.execute("SELECT payload FROM integra_publicacoes WHERE codigo=?", (cod,)).fetchone()
            if row:
                pubs.append(json.loads(row[0]))
    p1, p2, p3 = montar_mensagem(pubs, resumo, c["PANEL_URL"], c["INCLUIR_PARTES"])
    alvos = destinatarios(store, c)
    with store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        for nome in alvos:
            db.execute("INSERT OR IGNORE INTO whatsapp_integra_outbox(lote,username,state,created,p1,p2,p3) "
                       "VALUES(?,?,'pendente',?,?,?,?)", (lote, nome, now(), p1, p2, p3))
    return lote


def post_template(c: dict, phone: str, p1: str, p2: str, p3: str) -> str:
    payload = {"messaging_product": "whatsapp", "to": phone, "type": "template", "template": {
        "name": c["TEMPLATE_PUBLICACOES"], "language": {"code": c["LANGUAGE"] or "pt_BR"},
        "components": [{"type": "body", "parameters": [
            {"type": "text", "text": p1}, {"type": "text", "text": p2}, {"type": "text", "text": p3}]}]}}
    req = urllib.request.Request(
        "https://graph.facebook.com/" + c["API_VERSION"] + "/" + c["PHONE_NUMBER_ID"] + "/messages",
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + c["TOKEN"], "Content-Type": "application/json"})

    class SemRedirecionar(urllib.request.HTTPRedirectHandler):  # nunca repassar o token
        def redirect_request(self, *args):
            return None

    with urllib.request.build_opener(SemRedirecionar()).open(req, timeout=20) as resp:
        data = json.loads(resp.read(65536))
    mid = data.get("messages", [{}])[0].get("id")
    if not isinstance(mid, str) or not mid.startswith("wamid."):
        raise ValueError("RESPOSTA_INDETERMINADA")
    return mid


def texto_livre(p1: str, p2: str, p3: str) -> str:
    """Mesma mensagem do template, em texto livre (UazAPI permite quebras de linha)."""
    linhas = "\n".join(x.strip() for x in p2.split(" | "))
    return ("Robô Peres & Javarotti - novas publicações no INTEGRA.\n"
            f"Resumo: {p1}\n\nProcessos:\n{linhas}\n\nDetalhes: {p3}\n"
            "Mensagem automática para a equipe interna. Confira no INTEGRA antes de qualquer providência.\n"
            "Para consultar, responda: ajuda")


def post_uazapi(c: dict, phone: str, p1: str, p2: str, p3: str) -> str:
    from integrations import uazapi
    return uazapi.enviar_texto(phone, texto_livre(p1, p2, p3))


def enviar_pendentes(store, send=None) -> dict:
    c = cfg()
    if send is None:
        send = post_uazapi if c.get("PROVIDER") == "uazapi" else post_template
    erros = problemas_config(c)
    if erros:
        return {"enviado": 0, "motivo": "CONFIG_INCOMPLETA: " + "; ".join(erros)}
    preparar(store)
    alvos = destinatarios(store, c)
    contagem = {"aceito_api": 0, "recusado": 0, "reconciliar": 0, "cancelado": 0}
    with store.db() as db:
        itens = db.execute("SELECT lote,username,p1,p2,p3 FROM whatsapp_integra_outbox "
                           "WHERE state='pendente' ORDER BY created LIMIT 20").fetchall()
    for it in itens:
        try:
            enforce(store, ACAO)   # pausa, modo erro e regra de revisao do painel
        except Blocked as exc:
            return {**contagem, "motivo": f"BLOQUEADO: {exc}"}
        nome, lote = it["username"], it["lote"]
        phone = alvos.get(nome)
        with store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not phone:
                db.execute("UPDATE whatsapp_integra_outbox SET state='cancelado',updated=? "
                           "WHERE lote=? AND username=? AND state='pendente'", (now(), lote, nome))
                contagem["cancelado"] += 1
                continue
            # Intencao gravada antes da rede: queda no meio = "reconciliar", nunca reenvio cego.
            if not db.execute("UPDATE whatsapp_integra_outbox SET state='reconciliar',updated=? "
                              "WHERE lote=? AND username=? AND state='pendente'",
                              (now(), lote, nome)).rowcount:
                continue
        try:
            mid, estado = send(c, phone, it["p1"], it["p2"], it["p3"]), "aceito_api"
        except urllib.error.HTTPError as exc:
            mid, estado = "", ("recusado" if 400 <= exc.code < 500 else "reconciliar")
        except Exception:
            mid, estado = "", "reconciliar"
        contagem[estado] += 1
        with store.db() as db:
            db.execute("UPDATE whatsapp_integra_outbox SET state=?,message_id=?,updated=? "
                       "WHERE lote=? AND username=?", (estado, mid, now(), lote, nome))
            store._audit(db, {"action": EVENTO, "actor": "robo", "result": estado,
                              "recipient_key": nome, "lote": lote})
    return contagem


def avisar(store, codigos: list[str], resumo: dict) -> dict:
    """Chamado por executar_integra.py depois de gravar. Nunca derruba a leitura."""
    c = cfg()
    if not c["INTEGRA_ENABLED"]:
        return {"motivo": "WA_INTEGRA_ENABLED desligado"}
    lote = enfileirar(store, codigos, resumo)
    resultado = enviar_pendentes(store)
    resultado["lote"] = lote or "sem novidades"
    return resultado
