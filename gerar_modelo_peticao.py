from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from pathlib import Path

Path("modelos").mkdir(exist_ok=True)

doc = Document()

style = doc.styles["Normal"]
style.font.name = "Times New Roman"
style.font.size = Pt(12)

p = doc.add_paragraph()
run = p.add_run("EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO")
run.bold = True
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

doc.add_paragraph()

p = doc.add_paragraph()
p.add_run("Processo nº ").bold = True
p.add_run("{{processo}}")
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

doc.add_paragraph()

texto_corpo = (
    "O(A) advogado(a) {{advogado}}, vem, respeitosamente, à presença de "
    "Vossa Excelência, requerer a juntada da guia de custas gerada em "
    "{{data}}, conforme documento anexo."
)
p = doc.add_paragraph(texto_corpo)
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

doc.add_paragraph()

p = doc.add_paragraph("Termos em que,")
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

p = doc.add_paragraph("Pede deferimento.")
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

doc.add_paragraph()

p = doc.add_paragraph("{{data}}")
p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

doc.add_paragraph()
doc.add_paragraph()

p = doc.add_paragraph("_______________________________")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph("{{advogado}}")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER

p = doc.add_paragraph("OAB/PR XXXXX")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER

saida = "modelos/peticao_juntada_guia.docx"
doc.save(saida)
print(f"Modelo gerado com sucesso: {saida}")