import httpx
from core.config import settings
from core.audit import get_logger

log = get_logger("datajud")

class DataJudClient:
    """
    Consulta a API Pública do DataJud (CNJ).
    Retorna METADADOS de movimentações. NÃO acessa autos completos.
    """

    def __init__(self):
        self.base = settings.DATAJUD_BASE_URL
        self.headers = {
            "Authorization": f"APIKey {settings.DATAJUD_API_KEY}",
            "Content-Type": "application/json",
        }

    def buscar_por_numero(self, numero_cnj: str, tribunal: str = "tjpr") -> dict:
        """
        Busca metadados do processo por número CNJ.
        O índice do DataJud segue o padrão: api_publica_<tribunal>
        """
        index = f"api_publica_{tribunal.lower()}"
        url = f"{self.base}/{index}/_search"

        numero_limpo = numero_cnj.replace("-", "").replace(".", "").strip()

        payload = {
            "query": {
                "match": {
                    "numeroProcesso": numero_limpo
                }
            }
        }

        try:
            with httpx.Client(timeout=30) as client:
                r = client.post(url, json=payload, headers=self.headers)
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            log.error(f"Erro ao consultar DataJud: {e}")
            return {"numero_cnj": numero_cnj, "hits": []}

        hits = data.get("hits", {}).get("hits", [])
        log.info(f"DataJud: {len(hits)} resultado(s) para {numero_cnj}")
        return {"numero_cnj": numero_cnj, "hits": hits}