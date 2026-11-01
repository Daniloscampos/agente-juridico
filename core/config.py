import os
from dotenv import load_dotenv

load_dotenv()


def _int(name: str, default: int) -> int:
    valor = os.getenv(name, "").strip()
    return int(valor) if valor else default


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "sim", "yes"}


class Settings:
    # INTEGRA ---------------------------------------------------------------
    INTEGRA_URL = os.getenv("INTEGRA_URL", "https://www.integra.adv.br/")
    # Pagina de login validada em 08/10/2026 (campos txtUsuario / txtSenha).
    INTEGRA_LOGIN_URL = os.getenv("INTEGRA_LOGIN_URL", "https://www.integra.adv.br/login-integra.asp")
    # Opcional: endereco direto da tela Publicacoes. Vazio = abrir pelo menu "Publicações".
    INTEGRA_PUBLICACOES_URL = os.getenv("INTEGRA_PUBLICACOES_URL", "")
    INTEGRA_USER = os.getenv("INTEGRA_USER", "")
    INTEGRA_PASS = os.getenv("INTEGRA_PASS", "")
    # manual = o robo abre o Chrome e espera o login humano (padrao seguro).
    # auto   = usa INTEGRA_USER/INTEGRA_PASS do .env (somente conta tecnica do robo).
    INTEGRA_LOGIN_MODE = os.getenv("INTEGRA_LOGIN_MODE", "manual").strip().lower()
    INTEGRA_LOGIN_TIMEOUT = _int("INTEGRA_LOGIN_TIMEOUT", 300)
    INTEGRA_HEADLESS = _bool("INTEGRA_HEADLESS")
    # Perfil exclusivo do Chrome do robo. Nunca aponte para o perfil do seu Chrome pessoal.
    INTEGRA_PROFILE_DIR = os.getenv("INTEGRA_PROFILE_DIR", "./.browser/integra")
    # Nesta etapa o robo so LE. Gravar no INTEGRA continua bloqueado no codigo.
    INTEGRA_SOMENTE_LEITURA = True

    # DataJud ---------------------------------------------------------------
    DATAJUD_API_KEY = os.getenv("DATAJUD_API_KEY", "")
    DATAJUD_BASE_URL = os.getenv("DATAJUD_BASE_URL", "https://api-publica.datajud.cnj.jus.br")

    # Google Drive ----------------------------------------------------------
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "./credentials/google-service-account.json")
    GOOGLE_DRIVE_ROOT_FOLDER_ID = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "")

    # Bancos ----------------------------------------------------------------
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./agente.db")
    # Mesmo banco do painel (pausa, limites e auditoria encadeada).
    AGENT_DB = os.getenv("AGENT_DB", "var/operational.sqlite")

    # Dashboard -------------------------------------------------------------
    DASHBOARD_PORT = _int("DASHBOARD_PORT", 8000)

    # Selenium --------------------------------------------------------------
    CHROME_DRIVER_PATH = os.getenv("CHROME_DRIVER_PATH", "")  # opcional, Selenium Manager resolve
    SELENIUM_TIMEOUT = _int("SELENIUM_TIMEOUT", 20)


settings = Settings()
