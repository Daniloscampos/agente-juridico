"""Ciclo SOMENTE LEITURA do robo no INTEGRA: publicacoes do filtro padrao da tela.

Uso (PowerShell, na pasta do projeto):
  & ".\\.venv\\Scripts\\python.exe" .\\executar_integra.py                 # le o INTEGRA ao vivo
  & ".\\.venv\\Scripts\\python.exe" .\\executar_integra.py --html arquivo.txt  # le um HTML salvo (offline)
  & ".\\.venv\\Scripts\\python.exe" .\\executar_integra.py --sem-gravar     # nao grava no banco

Nao executa main.py, nao gera guia/peticao, nao envia ao Drive e nao escreve no INTEGRA.
Codigos de saida: 0 = ok | 2 = pausado/bloqueado | 3 = INTEGRA indisponivel | 4 = layout inesperado
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from core import control  # noqa: E402
from core.audit import get_logger  # noqa: E402
from core.config import settings  # noqa: E402
from core.policy import Blocked, enforce  # noqa: E402
from core.store import Store  # noqa: E402
from integrations.integra_parser import EstruturaInesperada, parse_listagem  # noqa: E402

log = get_logger("executar_integra")

# Leitura do INTEGRA e classificada como "agenda" (acao AUTO ja existente em core/policy.py).
ACAO_POLITICA = "agenda"


def _sem_caminho(texto: str) -> str:
    """Remove o caminho da pasta do usuario (ex.: C:\\Users\\nome) antes de ir para a auditoria."""
    return texto.replace(str(Path.home()), "~")


def verificar_pausas(store: Store) -> None:
    """Respeita os DOIS controles de pausa: arquivo .paused e painel (tabela control)."""
    if control.is_paused():
        raise Blocked("AGENTE_PAUSADO_ARQUIVO_.paused")
    enforce(store, ACAO_POLITICA)  # pausa do painel, modo erro e regra de revisao


def ler_ao_vivo() -> str:
    from integrations.integra import IntegraClient, IntegraIndisponivel
    try:
        with IntegraClient() as integra:
            integra.login()
            try:
                integra.abrir_publicacoes()
                return integra.html_listagem_publicacoes()
            except IntegraIndisponivel as exc:
                integra.diagnostico(str(exc))  # salva em saida\\diagnostico_integra_*
                raise
    except Blocked:
        raise
    except Exception as exc:  # WebDriverException, TimeoutException etc. = falha, nunca "zero"
        raise IntegraIndisponivel(f"ERRO_NAVEGADOR:{type(exc).__name__}") from exc


def salvar_relatorio(resultado, resumo: dict) -> Path:
    saida = ROOT / "saida"
    saida.mkdir(exist_ok=True)
    arq = saida / f"integra_publicacoes_{datetime.now():%Y%m%d_%H%M%S}.json"
    arq.write_text(json.dumps({
        "gerado_em": datetime.now().isoformat(timespec="seconds"),
        "resumo": resumo,
        "publicacoes": [p.to_dict() for p in resultado.publicacoes],
        "aviso": "Uso interno. Contem dados de partes. Nao compartilhar fora do escritorio.",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return arq


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Leitura somente-leitura das publicacoes do INTEGRA")
    ap.add_argument("--html", help="Arquivo com o HTML/Response de publicacoesListar.asp (modo offline)")
    ap.add_argument("--sem-gravar", action="store_true", help="Nao grava no banco do painel")
    args = ap.parse_args(argv)

    store = Store(settings.AGENT_DB)
    try:
        if not args.html:
            verificar_pausas(store)  # offline nao toca sistemas externos
    except Blocked as exc:
        log.warning(f"BLOQUEADO: {exc}")
        print(f"RESULTADO=BLOQUEADO ({exc})")
        return 2

    try:
        html = Path(args.html).read_text(encoding="utf-8", errors="replace") if args.html else ler_ao_vivo()
        resultado = parse_listagem(html)
    except EstruturaInesperada as exc:
        store.event(action="integra_publicacoes", actor="robo", result="erro", erro=f"LAYOUT:{exc}")
        print(f"RESULTADO=LAYOUT_INESPERADO ({exc}) - nada foi gravado")
        return 4
    except Blocked as exc:  # inclui IntegraIndisponivel
        store.event(action="integra_publicacoes", actor="robo", result="erro", erro=_sem_caminho(str(exc))[:200])
        print(f"RESULTADO=INTEGRA_INDISPONIVEL ({exc}) - isto NAO significa zero publicacoes")
        return 3

    if args.sem_gravar:
        from integrations.integra_publicacoes import preparar  # noqa: F401  (valida import)
        resumo = {"lidas": len(resultado.publicacoes), "rodape_exibindo": resultado.exibindo,
                  "rodape_total": resultado.total, "listagem_completa": resultado.completo,
                  "vinculo_pendente": sum(1 for p in resultado.publicacoes if not p.processos)}
    else:
        from integrations.integra_publicacoes import gravar
        novos: list = []
        resumo = gravar(store, resultado, origem="arquivo" if args.html else "INTEGRA", novos_out=novos)
        if not args.html:  # aviso so para leitura real do INTEGRA, nunca para arquivo de teste
            try:
                from integrations.whatsapp_integra import avisar
                wa = avisar(store, novos, resumo)
                print("WHATSAPP=" + json.dumps(wa, ensure_ascii=False))
            except Exception as exc:  # falha no aviso nunca invalida a leitura
                log.warning(f"WHATSAPP falhou: {type(exc).__name__}")  # so o tipo: nada de token/telefone
                store.event(action="aviso_integra_publicacoes", actor="robo", result="erro",
                            erro=type(exc).__name__)
                print(f"WHATSAPP=ERRO ({type(exc).__name__}) - leitura gravada normalmente")

    arq = salvar_relatorio(resultado, resumo)
    print("RESULTADO=OK" if resultado.completo else "RESULTADO=PARCIAL (rodape nao confere com as linhas)")
    print(json.dumps(resumo, ensure_ascii=False))
    print(f"Relatorio: {arq}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
