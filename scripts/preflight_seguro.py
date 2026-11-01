"""Diagnostico local sem rede, sem envio e sem expor credenciais.
Uso: .\\.venv\\Scripts\\python.exe .\\scripts\\preflight_seguro.py
"""
from pathlib import Path
import ast, os, sys, importlib.util
ROOT = Path(__file__).resolve().parents[1]
checks = []
def check(name, passed, detail=''):
    checks.append((name, bool(passed)))
    print(f"[{'OK' if passed else 'PENDENTE'}] {name}" + (f' - {detail}' if detail else ''))
    return passed
for rel in ('scripts/atendente_whatsapp.py','integrations/ia_openai.py','integrations/ia_orquestrador.py','integrations/atendente.py','integrations/whatsapp_integra.py','integrations/integra.py','integrations/integra_parser.py','integrations/integra_publicacoes.py','core/config.py','core/policy.py','core/control.py'):
    p=ROOT/rel
    if not p.is_file():
        check(rel,False,'arquivo nao encontrado'); continue
    try:
        ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
        check(rel,True,'sintaxe')
    except (SyntaxError,UnicodeError) as exc:
        check(rel,False,type(exc).__name__)
check('ambiente virtual',Path(sys.prefix).resolve()!=Path(sys.base_prefix).resolve())
check('arquivo .env', (ROOT/'.env').is_file())
check('python-dotenv',importlib.util.find_spec('dotenv') is not None)
check('selenium',importlib.util.find_spec('selenium') is not None)
if importlib.util.find_spec('dotenv') and (ROOT/'.env').is_file():
    from dotenv import dotenv_values
    vals=dotenv_values(ROOT/'.env')
    for k in ('GEMINI_API_KEY','UAZAPI_TOKEN','UAZAPI_URL'):
        check(k,bool(vals.get(k)),'preenchido' if vals.get(k) else 'ausente/vazio')
    for k in ('WA_IA_ENABLED','WA_INTEGRA_ENABLED','WA_ATENDENTE_ENABLED','IA_PROVEDORES','WA_PROVIDER'):
        print(f'[INFO] {k}={vals.get(k,"(ausente)")}')
    check('IA_PROVEDORES inclui gemini', 'gemini' in [x.strip().lower() for x in (vals.get('IA_PROVEDORES') or '').split(',')])
    check('somente equipe interna', (ROOT/'scripts/manage_whatsapp.py').is_file())
    check('gitignore protege .env', (ROOT/'.gitignore').is_file() and any(x.strip() in ('.env','*.env','.env*') for x in (ROOT/'.gitignore').read_text(encoding='utf-8',errors='replace').splitlines()))
print(f'RESUMO: {sum(ok for _,ok in checks)}/{len(checks)} verificacoes OK; nenhuma conexao externa ou envio realizado')
raise SystemExit(0 if all(ok for _,ok in checks) else 1)
