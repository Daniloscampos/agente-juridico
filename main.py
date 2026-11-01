from core import control
import asyncio
from pathlib import Path
from core.database import init_db, registrar_execucao
from core.audit import get_logger
from integrations.integra import IntegraClient
from integrations.projudi_tjpr import ProjudiTJPR
from integrations.datajud import DataJudClient
from integrations.drive import DriveClient
from skills.gerar_guia import GeradorGuia
from skills.gerar_peticao import GeradorPeticao
from skills.organizar_drive import pasta_do_processo

log = get_logger("main")

def executar_poc():    
    if control.is_paused():
        log.warning("Agente pausado. Nenhuma ação será executada.")
        return
    init_db()
    Path("./saida").mkdir(exist_ok=True)

    with IntegraClient() as integra:
        # 1. Ler tarefa no INTEGRA
        tarefas = integra.listar_tarefas()
        if not tarefas:
            log.warning("Nenhuma tarefa encontrada no INTEGRA.")
            return

        tarefa = tarefas[0]
        numero_cnj = tarefa["processo"]
        log.info(f"Executando tarefa: {tarefa['descricao']} | Processo: {numero_cnj}")

        # 2. Consultar Projudi TJPR (público, sem CPF)
        projudi = ProjudiTJPR(integra.driver)
        try:
            dados = projudi.consultar_por_numero_cnj(numero_cnj)
        except Exception as e:
            registrar_execucao(
                processo=numero_cnj, tarefa=tarefa["descricao"], origem="INTEGRA",
                acao="consultar_projudi", resultado="erro", erro=str(e),
            )
            raise

        # 3. Consultar DataJud (metadados)
        datajud = DataJudClient()
        try:
            meta = datajud.buscar_por_numero(numero_cnj, tribunal="tjpr")
        except Exception as e:
            log.warning(f"DataJud indisponível: {e}")
            meta = {"hits": []}

        # 4. Gerar guia
        guia_pdf = f"./saida/guia_{numero_cnj.replace('/', '-')}.pdf"
        gerador = GeradorGuia(integra.driver)
        gerador.gerar_tjpr(numero_cnj, guia_pdf)

        # 5. Gerar petição
        peticao_docx = f"./saida/peticao_{numero_cnj.replace('/', '-')}.docx"
        modelo = "./modelos/peticao_juntada_guia.docx"
        if Path(modelo).exists():
            GeradorPeticao(modelo).gerar(
                variaveis={
                    "processo": numero_cnj,
                    "data": "01/10/2026",
                    "advogado": "Dr. Peres",
                    "guia": guia_pdf,
                },
                saida_path=peticao_docx,
            )
        else:
            log.warning(f"Modelo não encontrado: {modelo}")

        # 6. Salvar no Drive
        pasta_id = pasta_do_processo(numero_cnj)
        drive = DriveClient()
        link_guia = drive.salvar_arquivo(guia_pdf, pasta_id)
        link_peticao = drive.salvar_arquivo(peticao_docx, pasta_id) if Path(peticao_docx).exists() else None

        # 7. Registrar retorno no INTEGRA
        msg = f"Guia gerada • Processo {numero_cnj} • Arquivo salvo • Aguardando revisão."
        integra.registrar_retorno(tarefa["id"], "CONCLUIDO", msg)

        # 8. Auditoria
        registrar_execucao(
            processo=numero_cnj,
            tarefa=tarefa["descricao"],
            origem="INTEGRA",
            acao="gerar_guia+peticao",
            resultado="sucesso",
            arquivo_gerado=guia_pdf,
            local_salvo=link_guia,
            mensagem=msg,
        )

        log.info("POC concluída com sucesso.")


if __name__ == "__main__":
    executar_poc()