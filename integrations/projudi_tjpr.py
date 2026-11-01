import time
from selenium.webdriver.common.by import By
from core.audit import get_logger

log = get_logger("projudi_tjpr")

PROJUDI_URL = "https://projudi.tjpr.jus.br/projudi/"

class ProjudiTJPR:
    """
    Consulta processual pública no Projudi/TJPR.
    IMPORTANTE: NÃO usa CPF nem credenciais pessoais. Usa número CNJ.
    """

    def __init__(self, driver):
        self.driver = driver

    def consultar_por_numero_cnj(self, numero_cnj: str) -> dict:
        """
        Acessa a página pública do Projudi e busca o processo pelo número CNJ.
        """
        log.info(f"Consultando Projudi TJPR: {numero_cnj}")

        self.driver.get(PROJUDI_URL)
        time.sleep(3)

        try:
            # TODO: ajustar seletor real do link "Consulta Processual Pública"
            link = self.driver.find_element(By.LINK_TEXT, "Consulta Processual Pública")
            link.click()
            time.sleep(3)
        except Exception as e:
            log.warning(f"Link de consulta pública não encontrado: {e}")
            return {"numero_cnj": numero_cnj, "movimentacoes": []}

        try:
            # TODO: ajustar seletor real do campo de número do processo
            campo = self.driver.find_element(By.NAME, "numeroProcesso")
            campo.clear()
            campo.send_keys(numero_cnj)
            self.driver.find_element(By.XPATH, "//button[contains(text(), 'Pesquisar')]").click()
            time.sleep(3)
        except Exception as e:
            log.warning(f"Erro ao pesquisar processo: {e}")
            return {"numero_cnj": numero_cnj, "movimentacoes": []}

        movimentacoes = []
        try:
            rows = self.driver.find_elements(By.CSS_SELECTOR, "table.movimentacoes tbody tr")
            for row in rows:
                data = row.find_element(By.CSS_SELECTOR, "td.data").text
                texto = row.find_element(By.CSS_SELECTOR, "td.descricao").text
                movimentacoes.append({"data": data.strip(), "texto": texto.strip()})
        except Exception as e:
            log.warning(f"Nenhuma movimentação encontrada: {e}")

        log.info(f"{len(movimentacoes)} movimentações públicas encontradas")
        return {"numero_cnj": numero_cnj, "movimentacoes": movimentacoes}