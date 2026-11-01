from pathlib import Path

# Arquivo sentinela: se existir, o agente está pausado
PAUSE_FILE = Path(".paused")


def is_paused() -> bool:
    """Retorna True se o agente estiver pausado."""
    return PAUSE_FILE.exists()


def pausar() -> None:
    """Cria o arquivo sentinela para pausar o agente."""
    PAUSE_FILE.touch()


def retomar() -> None:
    """Remove o arquivo sentinela para retomar o agente."""
    if PAUSE_FILE.exists():
        PAUSE_FILE.unlink()


def status() -> str:
    """Retorna o status atual do agente."""
    return "pausado" if is_paused() else "operando"