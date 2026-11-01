import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from core.config import settings
from core.audit import get_logger

log = get_logger("drive")

SCOPES = ["https://www.googleapis.com/auth/drive"]

class DriveClient:
    def __init__(self):
        creds = service_account.Credentials.from_service_account_file(
            settings.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
        )
        self.service = build("drive", "v3", credentials=creds)

    def garantir_pasta(self, nome: str, parent_id: str) -> str:
        """Cria ou retorna a pasta com o nome dentro do parent_id."""
        q = (
            f"name='{nome}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        res = self.service.files().list(q=q, fields="files(id, name)").execute()
        arquivos = res.get("files", [])
        if arquivos:
            return arquivos[0]["id"]

        metadata = {
            "name": nome,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        pasta = self.service.files().create(body=metadata, fields="id").execute()
        log.info(f"Pasta criada no Drive: {nome}")
        return pasta["id"]

    def salvar_arquivo(self, caminho_local: str, parent_id: str, nome: str = None) -> str:
        nome = nome or os.path.basename(caminho_local)
        media = MediaFileUpload(caminho_local, resumable=True)
        metadata = {"name": nome, "parents": [parent_id]}
        arq = self.service.files().create(
            body=metadata, media_body=media, fields="id, webViewLink"
        ).execute()
        log.info(f"Arquivo salvo no Drive: {nome} ({arq['id']})")
        return arq["webViewLink"]