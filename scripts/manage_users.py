"""Run directly on the protected server; password is read without echo."""
import argparse
import getpass
import os
from pathlib import Path
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.auth import Auth
from core.store import Store


def main():
    parser=argparse.ArgumentParser(description='Administrar acesso ao dashboard')
    parser.add_argument('action',choices=['create','reset-password'])
    parser.add_argument('username')
    parser.add_argument('--role',choices=['admin','reader'],default='reader')
    parser.add_argument('--email',help='Email institucional para recuperacao')
    args=parser.parse_args()
    if not sys.stdin.isatty():parser.error('Execute em terminal interativo; nao envie senha por argumento ou arquivo')
    os.umask(0o077)
    password=getpass.getpass('Senha (minimo 12 caracteres): ')
    if password!=getpass.getpass('Confirme a senha: '):parser.error('Senhas diferentes')
    auth=Auth(Store(os.environ.get('AGENT_DB','var/operational.sqlite')))
    try:
        if args.action=='create':auth.create_user(args.username,password,args.role,args.email)
        else:auth.reset_password(args.username,password)
    except (ValueError,sqlite3.IntegrityError) as exc:
        parser.error('Usuario ja existe' if isinstance(exc,sqlite3.IntegrityError) else str(exc))
    print('Acesso atualizado. Nenhuma senha foi exibida.')
if __name__=='__main__':main()
