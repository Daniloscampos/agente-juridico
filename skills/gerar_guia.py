import time
from selenium.webdriver.common.by import By
from core.audit import get_logger

log = get_logger("gerar_guia")

class GeradorGuia:
    """
    Gera guia de custas a partir de páginas públicas dos tribunais.
    NÃO usa CPF, NÃO efetua pagamento.
    """

    def __init__(self, driver):
        self.driver = driver

    def gerar_tjpr(self, numero_cnj: str, saida_pdf: str) -> str:
        """
        Acessa o portal de custas do TJPR, gera a guia e salva em PDF.
        TODO: ajustar URL e seletores conforme o portal real.
        """
        log.info(f"Gerando guia TJPR para {numero_cnj}")

        self.driver.get("https://www.tjpr.jus.br/guias")
        time.sleep(3)

        try:
            campo = self.driver.find_element(By.NAME, "processo")
            campo.clear()
            campo.send_keys(numero_cnj)
            self.driver.find_element(By.XPATH, "//button[contains(text(), 'Gerar Guia')]").click()
            time.sleep(5)

            # Salvar como PDF via comando do Chrome
            result = self.driver.execute_cdp_cmd("Page.printToPDF", {"format": "A4"})
            import base64
            with open(saida_pdf, "wb") as f:
                f.write(base64.b64decode(result["data"]))
            log.info(f"Guia salva em {saida_pdf}")
        except Exception as e:
            log.error(f"Erro ao gerar guia: {e}")
            raise

        return saida_pdf