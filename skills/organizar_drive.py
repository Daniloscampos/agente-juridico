from integrations.drive import DriveClient
from core.config import settings
from core.audit import get_logger

log = get_logger("organizar_drive")

def pasta_do_processo(numero_cnj: str) -> str:
    """
    Garante a estrutura:
    ROOT / <ano> / <numero_cnj> /
    Retorna o ID da pasta do processo.
    """
    drive = DriveClient()
    ano = numero_cnj.split("-")[-1] if "-" in numero_cnj else "sem-ano"
    pasta_ano = drive.garantir_pasta(ano, settings.GOOGLE_DRIVE_ROOT_FOLDER_ID)
    pasta_proc = drive.garantir_pasta(numero_cnj.replace("/", "-"), pasta_ano)
    return pasta_proc