"""Gravacao idempotente das publicacoes lidas do INTEGRA no banco do painel.

* Usa o mesmo SQLite do painel (AGENT_DB), em tabela propria.
* Reler a mesma publicacao NAO duplica registro (chave = codigo do INTEGRA).
* Publicacao sem processo fica com status "vinculo_pendente".
* A auditoria encadeada recebe apenas contagens — sem nomes de partes.
"""
from __future__ import annotations

import hashlib
import json

from core.store import now
from integrations.integra_parser import ResultadoListagem

SCHEMA = """
CREATE TABLE IF NOT EXISTS integra_publicacoes(
    codigo TEXT PRIMARY KEY,
    data_disponibilizacao TEXT NOT NULL DEFAULT '',
    data_inclusao TEXT NOT NULL DEFAULT '',
    orgao_comarca TEXT NOT NULL DEFAULT '',
    processos TEXT NOT NULL DEFAULT '[]',
    status_vinculo TEXT NOT NULL,
    conteudo_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    primeira_leitura TEXT NOT NULL,
    ultima_leitura TEXT NOT NULL,
    situacao_robo TEXT NOT NULL DEFAULT 'lida_lista'
);
CREATE INDEX IF NOT EXISTS ix_integra_pub_vinculo ON integra_publicacoes(status_vinculo);
"""


def preparar(store) -> None:
    with store.db() as c:
        c.executescript(SCHEMA)


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def gravar(store, resultado: ResultadoListagem, origem: str = "INTEGRA", novos_out: list | None = None) -> dict:
    """novos_out (opcional) recebe os codigos novos ou alterados — usado pelo aviso de WhatsApp."""
    preparar(store)
    stamp = now()
    novas = atualizadas = iguais = 0
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        for pub in resultado.publicacoes:
            d = pub.to_dict()
            payload = json.dumps(d, ensure_ascii=False, sort_keys=True)
            h = _hash(payload)
            processos = json.dumps([p["numero_cnj"] for p in d["processos"]], ensure_ascii=False)
            row = c.execute("SELECT conteudo_hash FROM integra_publicacoes WHERE codigo=?", (pub.codigo,)).fetchone()
            if row is None:
                c.execute(
                    "INSERT INTO integra_publicacoes(codigo,data_disponibilizacao,data_inclusao,orgao_comarca,"
                    "processos,status_vinculo,conteudo_hash,payload,primeira_leitura,ultima_leitura) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (pub.codigo, pub.data_disponibilizacao, pub.data_inclusao, pub.orgao_comarca, processos,
                     pub.status_vinculo, h, payload, stamp, stamp))
                novas += 1
                if novos_out is not None:
                    novos_out.append(pub.codigo)
            elif row[0] != h:
                # Ex.: o escritorio vinculou o processo depois. Atualiza e registra.
                c.execute(
                    "UPDATE integra_publicacoes SET processos=?,status_vinculo=?,conteudo_hash=?,payload=?,"
                    "orgao_comarca=?,ultima_leitura=? WHERE codigo=?",
                    (processos, pub.status_vinculo, h, payload, pub.orgao_comarca, stamp, pub.codigo))
                atualizadas += 1
                if novos_out is not None:
                    novos_out.append(pub.codigo)
            else:
                c.execute("UPDATE integra_publicacoes SET ultima_leitura=? WHERE codigo=?", (stamp, pub.codigo))
                iguais += 1
        resumo = {
            "lidas": len(resultado.publicacoes),
            "novas": novas,
            "atualizadas": atualizadas,
            "sem_alteracao": iguais,
            "vinculo_pendente": sum(1 for p in resultado.publicacoes if not p.processos),
            "multiplos_processos": sum(1 for p in resultado.publicacoes if len(p.processos) > 1),
            "rodape_exibindo": resultado.exibindo,
            "rodape_total": resultado.total,
            "listagem_completa": resultado.completo,
        }
        store._audit(c, {"action": "integra_publicacoes", "actor": "robo", "origem": origem,
                         "result": "confirmado" if resultado.completo else "parcial", **resumo})
    return resumo
