from core.audit import get_logger
from core.database import registrar_execucao

log = get_logger("acompanhar_tarefas")

def acompanhar(integra) -> list:
    tarefas = integra.listar_tarefas()
    for t in tarefas:
        registrar_execucao(
            processo=t["processo"],
            tarefa=t["descricao"],
            origem="INTEGRA",
            acao="listar_tarefa",
            resultado="sucesso",
            mensagem=f"Tarefa {t['id']} identificada",
        )
    return tarefas