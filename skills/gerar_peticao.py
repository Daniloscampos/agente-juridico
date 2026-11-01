from pathlib import Path
from docx import Document
from core.audit import get_logger

log = get_logger("gerar_peticao")

class GeradorPeticao:
    """
    Gera petição simples a partir de modelo .docx do escritório.
    Substitui variáveis do tipo {{processo}}, {{advogado}}, {{data}}, {{guia}}.
    """

    def __init__(self, modelo_path: str):
        self.modelo_path = Path(modelo_path)

    def gerar(self, variaveis: dict, saida_path: str) -> str:
        doc = Document(str(self.modelo_path))

        def substituir(texto: str) -> str:
            for k, v in variaveis.items():
                texto = texto.replace(f"{{{{{k}}}}}", str(v))
            return texto

        for p in doc.paragraphs:
            for run in p.runs:
                run.text = substituir(run.text)

        for t in doc.tables:
            for row in t.rows:
                for cell in row.cells:
                    for p in cell.paragraphs:
                        for run in p.runs:
                            run.text = substituir(run.text)

        doc.save(saida_path)
        log.info(f"Petição gerada em {saida_path}")
        return saida_path