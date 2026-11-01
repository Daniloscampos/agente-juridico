"""Local dashboard in the original project; no robot activation."""
from pathlib import Path
import getpass
import os
import socket
import sys

ROOT = Path(__file__).resolve().parent

def main():
    if sys.version_info < (3, 12):
        print('Este pacote requer Python 3.12 ou superior.')
        return 1
    os.chdir(ROOT)
    # Preserve an existing configured database path; otherwise use the project default.
    os.environ.setdefault('AGENT_DB', str(ROOT / 'var' / 'operational.sqlite'))
    os.environ['DASH_COOKIE_SECURE'] = 'false'  # loopback-only HTTP
    try:
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 8000))
    except OSError:
        print('A porta 8000 esta ocupada. Feche outra instancia deste painel e tente novamente.')
        return 1
    from core.store import Store
    from core.auth import Auth
    store = Store(os.environ['AGENT_DB'])
    auth = Auth(store)
    with store.db() as c:
        registered = bool(c.execute('SELECT 1 FROM users WHERE active=1').fetchone())
    if not registered:
        print('Primeiro acesso: crie seu usuario administrador no painel.')
        username = input('Usuario (Enter para admin): ').strip() or 'admin'
        password = getpass.getpass('Senha (minimo 12 caracteres; nao aparece ao digitar): ')
        confirmation = getpass.getpass('Repita a senha: ')
        if password != confirmation:
            print('As senhas sao diferentes. Execute novamente para repetir o cadastro.')
            return 1
        try:
            auth.create_user(username, password, 'admin')
        except ValueError as exc:
            print(str(exc))
            return 1
        finally:
            password = confirmation = None
        print('Usuario criado. Entre com os dados que voce acabou de definir.')
    print('\nPAINEL ATUALIZADO: http://127.0.0.1:8000/')
    print('Painel carregado da pasta original: '+str(ROOT))
    print('Este comando inicia somente o painel; nao ativa o robo nem integra sistemas externos.\n')
    import uvicorn
    uvicorn.run('dashboard.app:app', host='127.0.0.1', port=8000)
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
