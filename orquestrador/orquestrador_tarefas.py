"""Etapa 65: ponte segura entre Agenda e orquestrador (sem execução autônoma)."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Callable, Iterable, Mapping
import json
import uuid

CAMPOS = ('data_hora', 'tipo', 'status', 'cliente', 'processo', 'descricao')

class TarefaInvalida(ValueError): pass
class FonteNaoHomologada(RuntimeError): pass

@dataclass(frozen=True)
class TarefaNormalizada:
    id_interno: str
    data_hora: str
    tipo: str
    status: str
    cliente: str
    processo: str
    descricao: str
    origem: str = 'INTEGRA'
    modo: str = 'SIMULACAO'


def normalizar_tarefa(registro: Mapping, *, modo: str = 'SIMULACAO') -> TarefaNormalizada:
    if modo not in ('SIMULACAO', 'HOMOLOGADO'):
        raise TarefaInvalida('Modo desconhecido')
    ausentes = [k for k in CAMPOS if k not in registro]
    if ausentes:
        raise TarefaInvalida('Campos ausentes: ' + ', '.join(ausentes))
    campos = {k: str(registro[k] or '').strip() for k in CAMPOS}
    if not campos['data_hora'] or not campos['tipo']:
        raise TarefaInvalida('Data/hora e tipo são obrigatórios')
    chave = '\x1f'.join(campos[k] for k in CAMPOS)
    ident = sha256(chave.encode('utf-8')).hexdigest()[:20]
    return TarefaNormalizada(id_interno=ident, **campos, modo=modo)


def preparar_fila(registros: Iterable[Mapping], *, fonte_homologada: bool = False) -> list[TarefaNormalizada]:
    """Deduplica, não executa tarefas, não envia mensagens e não persiste dados."""
    if fonte_homologada:
        # Não habilitar enquanto o parser de linhas da Etapa 64 não for homologado.
        raise FonteNaoHomologada('Integração real bloqueada até homologação da Etapa 64')
    unicos = {}
    for registro in registros:
        t = normalizar_tarefa(registro)
        unicos[t.id_interno] = t
    return list(unicos.values())


def classificar_para_painel(tarefa: TarefaNormalizada) -> dict:
    """Projeção SEM dados de cliente, processo ou descrição."""
    return {'id_interno': tarefa.id_interno, 'tipo': tarefa.tipo,
            'status': tarefa.status, 'data_hora': tarefa.data_hora,
            'origem': tarefa.origem, 'modo': tarefa.modo,
            'execucao_permitida': False, 'notificacao_permitida': False,
            'motivo': 'Aguardando homologação da fonte e autorização humana'}


def evento_auditoria(tarefa: TarefaNormalizada, acao: str = 'TAREFA_RECEBIDA_SIMULACAO') -> dict:
    return {'evento_id': str(uuid.uuid4()), 'instante_utc': datetime.now(timezone.utc).isoformat(),
            'tarefa_id': tarefa.id_interno, 'acao': acao,
            'modo': tarefa.modo, 'resultado': 'NAO_EXECUTADA'}


def gerar_preview(registros: Iterable[Mapping]) -> dict:
    fila = preparar_fila(registros)
    return {'total': len(fila), 'tarefas': [classificar_para_painel(t) for t in fila],
            'auditoria': [evento_auditoria(t) for t in fila]}

if __name__ == '__main__':
    exemplo = [{'data_hora':'2026-10-12 09:00', 'tipo':'GUIA', 'status':'NAOCONCLUIDO',
                'cliente':'CLIENTE_TESTE', 'processo':'PROCESSO_TESTE',
                'descricao':'Exemplo fictício para homologação'}]
    print(json.dumps(gerar_preview(exemplo), ensure_ascii=False, indent=2))
