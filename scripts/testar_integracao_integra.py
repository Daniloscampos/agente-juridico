"""Teste de integracao ponta a ponta com o INTEGRA - SOMENTE LEITURA.

Etapas (cada uma imprime OK/FALHA):
  T1 ambiente      Python >= 3.12, .venv, selenium instalado, pasta do projeto
  T2 configuracao  .env presente, modo de login, URL de login, perfil exclusivo
  T3 pausas        arquivo .paused e pausa do painel (ambas devem estar liberadas)
  T4 parser        le a amostra anonimizada (tests/fixtures) -> 6 publicacoes
  T5 login         abre o Chrome do robo e confirma Clientes/Processos/Agenda
  T6 publicacoes   abre Publicacoes, clica Pesquisar e le a listagem
  T7 conferencia   rodape "Exibindo N de M" == linhas lidas
  T8 gravacao      (somente com --gravar) grava no banco e confirma idempotencia

Nao grava no INTEGRA, nao abre publicacoes, nao executa main.py.

Uso:
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_integracao_integra.py
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_integracao_integra.py --somente-offline
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\testar_integracao_integra.py --gravar
"""
from __future__ import annotations

import argparse
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

RESULTADOS: list[dict] = []


def etapa(codigo: str, nome: str, ok: bool, detalhe: str = "") -> bool:
    RESULTADOS.append({"etapa": codigo, "nome": nome, "ok": ok, "detalhe": detalhe})
    print(f"[{'OK   ' if ok else 'FALHA'}] {codigo} {nome}" + (f" - {detalhe}" if detalhe else ""))
    return ok


def relatorio(final: str) -> int:
    saida = ROOT / "saida"
    saida.mkdir(exist_ok=True)
    arq = saida / f"teste_integracao_integra_{datetime.now():%Y%m%d_%H%M%S}.json"
    arq.write_text(json.dumps({"resultado": final, "etapas": RESULTADOS,
                               "gerado_em": datetime.now().isoformat(timespec="seconds")},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nRESULTADO_FINAL={final}\nRelatorio: {arq}")
    return 0 if final == "INTEGRACAO_VERIFICADA" or final == "OFFLINE_VERIFICADO" else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--somente-offline", action="store_true", help="Executa T1-T4, sem abrir o INTEGRA")
    ap.add_argument("--gravar", action="store_true", help="Inclui T8: grava as publicacoes no banco do painel")
    args = ap.parse_args(argv)

    # T1 -------------------------------------------------------------------
    py_ok = sys.version_info >= (3, 12)
    sel_ok = importlib.util.find_spec("selenium") is not None
    if not etapa("T1", "ambiente", py_ok and (sel_ok or args.somente_offline),
                 f"python {sys.version.split()[0]}; selenium={'sim' if sel_ok else 'NAO'}"):
        return relatorio("AMBIENTE_INVALIDO")

    # T2 -------------------------------------------------------------------
    from core.config import settings
    env_ok = (ROOT / ".env").is_file() or args.somente_offline
    modo = settings.INTEGRA_LOGIN_MODE
    modo_ok = modo in {"manual", "auto"} and (modo == "manual" or (settings.INTEGRA_USER and settings.INTEGRA_PASS))
    url_ok = settings.INTEGRA_LOGIN_URL.startswith("https://")
    perfil = Path(settings.INTEGRA_PROFILE_DIR).resolve()
    perfil_ok = "google\\chrome\\user data" not in str(perfil).lower()
    if not etapa("T2", "configuracao", env_ok and modo_ok and url_ok and perfil_ok,
                 f".env={'sim' if env_ok else 'NAO'}; modo={modo}; perfil={perfil}"):
        return relatorio("CONFIGURACAO_INVALIDA")

    # T3 -------------------------------------------------------------------
    from core import control
    from core.policy import Blocked
    from core.store import Store
    import executar_integra as ex
    store = Store(settings.AGENT_DB)
    try:
        ex.verificar_pausas(store)
        etapa("T3", "pausas liberadas", True, f".paused={control.status()}; painel={store.control()['mode']}")
        pausado = False
    except Blocked as exc:
        etapa("T3", "pausas liberadas", False, f"{exc} - retome pelo painel e/ou control.retomar()")
        pausado = True

    # T4 -------------------------------------------------------------------
    from integrations.integra_parser import parse_listagem
    amostra = ROOT / "tests" / "fixtures" / "publicacoes_integra_anonimizado.html"
    r = parse_listagem(amostra.read_text(encoding="utf-8"))
    pend = sum(1 for p in r.publicacoes if not p.processos)
    if not etapa("T4", "parser (amostra)", len(r.publicacoes) == 6 and r.completo and pend == 2,
                 f"{len(r.publicacoes)} lidas, {pend} vinculo pendente"):
        return relatorio("PARSER_INVALIDO")

    if args.somente_offline:
        return relatorio("OFFLINE_VERIFICADO")
    if pausado:
        return relatorio("BLOQUEADO_POR_PAUSA")

    # T5-T7 ------------------------------------------------------------------
    from integrations.integra import IntegraClient, IntegraIndisponivel
    from integrations.integra_parser import EstruturaInesperada
    try:
        with IntegraClient() as integra:
            integra.login()
            etapa("T5", "login INTEGRA", True, "ACESSO_VERIFICADO")
            try:
                integra.abrir_publicacoes()
                html = integra.html_listagem_publicacoes()
            except IntegraIndisponivel as exc:
                print("\n--- DIAGNOSTICO (sem dados pessoais) ---")
                print(integra.diagnostico(str(exc)))
                print("--- fim do diagnostico ---\n")
                raise
            vivo = parse_listagem(html)
            etapa("T6", "listagem de publicacoes", True, f"{len(vivo.publicacoes)} linha(s) lida(s)")
    except IntegraIndisponivel as exc:
        etapa("T5/T6", "acesso/leitura", False, str(exc))
        store.event(action="teste_integracao_integra", actor="robo", result="erro", erro=ex._sem_caminho(str(exc))[:200])
        return relatorio("INTEGRA_INDISPONIVEL")
    except EstruturaInesperada as exc:
        etapa("T6", "listagem de publicacoes", False, f"layout inesperado: {exc}")
        return relatorio("LAYOUT_INESPERADO")
    except Exception as exc:  # erro do Selenium/Chrome = falha de acesso, nunca "zero publicacoes"
        etapa("T5/T6", "acesso/leitura", False, f"ERRO_NAVEGADOR:{type(exc).__name__}")
        store.event(action="teste_integracao_integra", actor="robo", result="erro",
                    erro=f"ERRO_NAVEGADOR:{type(exc).__name__}")
        return relatorio("INTEGRA_INDISPONIVEL")

    conf = etapa("T7", "conferencia do rodape", vivo.completo,
                 f"Exibindo {vivo.exibindo} de {vivo.total}; linhas={len(vivo.publicacoes)}; "
                 f"vinculo_pendente={sum(1 for p in vivo.publicacoes if not p.processos)}")

    # T8 -------------------------------------------------------------------
    if args.gravar:
        from integrations.integra_publicacoes import gravar
        g1 = gravar(store, vivo)
        g2 = gravar(store, vivo)
        etapa("T8", "gravacao idempotente", g2["novas"] == 0 and store.verify(),
              f"1a: {g1['novas']} novas; 2a: {g2['novas']} novas; auditoria integra={store.verify()}")

    store.event(action="teste_integracao_integra", actor="robo",
                result="confirmado" if conf else "parcial", lidas=len(vivo.publicacoes))
    return relatorio("INTEGRACAO_VERIFICADA" if all(x["ok"] for x in RESULTADOS) else "INTEGRACAO_PARCIAL")


if __name__ == "__main__":
    raise SystemExit(main())
