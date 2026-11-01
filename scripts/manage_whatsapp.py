"""Register/remove an internal user on the protected host; never handles API tokens."""
import argparse
import json
import os
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.store import Store

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Autorizar WhatsApp de usuario interno')
    p.add_argument('action',choices=['add','remove']);p.add_argument('username')
    p.add_argument('--phone',help='Numero internacional, somente digitos')
    p.add_argument('--internal-consent',action='store_true',help='Confirma usuario interno e autorizacao para receber avisos')
    args=p.parse_args();store=Store(os.environ.get('AGENT_DB','var/operational.sqlite'))
    path=Path(os.environ.get('WA_RECIPIENTS_FILE','var/whatsapp-recipients.json'))
    with store.db() as db:
        try:user=db.execute('SELECT active FROM users WHERE username=?',(args.username,)).fetchone()
        except Exception:p.error('Cadastre primeiro o usuario de acesso ao painel.')
    data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    data=[i for i in data if i['username']!=args.username]
    if args.action=='add':
        if not user or not user[0]:p.error('Usuario do painel inexistente ou inativo.')
        if not args.internal_consent or not re.fullmatch(r'[1-9]\d{7,14}',args.phone or ''):p.error('Confirme usuario interno, autorizacao e numero internacional.')
        if any(i['phone']==args.phone for i in data):p.error('Numero ja associado a outro usuario.')
        data.append({'username':args.username,'phone':args.phone,'internal':True,'consent':True})
    path.parent.mkdir(parents=True,exist_ok=True)
    os.umask(0o077);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,indent=2),encoding='utf-8');os.replace(tmp,path)
    print('Cadastro interno atualizado. Nenhuma mensagem foi enviada.')
