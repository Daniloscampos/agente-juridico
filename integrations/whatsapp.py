"""Internal WhatsApp Cloud API notifications; no client sends or automatic retries."""
import json
import os
from pathlib import Path
import re
import urllib.request
import urllib.error
from core.policy import Blocked, enforce
from core.store import now

EVENTS = {'pausa', 'retomada', 'erro_critico', 'revisao_entrega', 'alterar_limite', 'workflow', 'finalizar'}
LABELS = {'pausa':'Agente pausado', 'retomada':'Execução habilitada', 'erro_critico':'Operação requer atenção',
          'revisao_entrega':'Revisão registrada', 'alterar_limite':'Regra de autonomia atualizada',
          'workflow':'Tarefa requer atenção', 'finalizar':'Estado da tarefa atualizado'}


def config():
    return {k:os.environ.get('WA_'+k,'') for k in ('ENABLED','TOKEN','PHONE_NUMBER_ID','API_VERSION','TEMPLATE','LANGUAGE','PANEL_URL','RECIPIENTS_FILE')}


def ready(c):
    return (c['ENABLED']=='true' and bool(c['TOKEN']) and bool(re.fullmatch(r'\d+',c['PHONE_NUMBER_ID']))
            and bool(re.fullmatch(r'v\d+\.\d+',c['API_VERSION']))
            and bool(re.fullmatch(r'[a-z0-9_]+',c['TEMPLATE'])) and c['PANEL_URL'].startswith('https://'))


def recipients(store,c):
    path=Path(c['RECIPIENTS_FILE'] or 'var/whatsapp-recipients.json')
    if not path.is_file():return {}
    data=json.loads(path.read_text(encoding='utf-8'))
    approved={}
    with store.db() as db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='users'").fetchone():return {}
        for item in data:
            name=item.get('username',''); phone=item.get('phone','')
            user=db.execute('SELECT active FROM users WHERE username=?',(name,)).fetchone()
            if user and user[0] and item.get('internal') is True and item.get('consent') is True and re.fullmatch(r'[1-9]\d{7,14}',phone):
                approved[name]=phone
    if len(set(approved.values()))!=len(approved):raise ValueError('DESTINATARIOS_DUPLICADOS')
    return approved


def status(store):
    c=config()
    try:count=len(recipients(store,c));valid=ready(c)
    except (ValueError,OSError,TypeError):count=0;valid=False
    with store.db() as db:
        counts=dict(db.execute('SELECT state,COUNT(*) FROM whatsapp_outbox GROUP BY state'))
    return {'configured':bool(valid and count), 'recipients':count, 'queue':counts,
            'note':'Aceito pela API não confirma entrega ou leitura. Pausa e revisão de avisos internos suspendem os envios.'}


def post_message(c,phone,label,reference):
    payload={'messaging_product':'whatsapp','to':phone,'type':'template','template':{
        'name':c['TEMPLATE'],'language':{'code':c['LANGUAGE'] or 'pt_BR'},'components':[{'type':'body','parameters':[
            {'type':'text','text':label},{'type':'text','text':reference},{'type':'text','text':c['PANEL_URL']}]}]}}
    req=urllib.request.Request('https://graph.facebook.com/'+c['API_VERSION']+'/'+c['PHONE_NUMBER_ID']+'/messages',
        data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+c['TOKEN'],'Content-Type':'application/json'},method='POST')
    # Never follow redirects with a bearer token.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:
        data=json.loads(response.read(65536))
    message=data.get('messages',[{}])[0].get('id')
    if not isinstance(message,str) or not message.startswith('wamid.'):raise ValueError('RESPOSTA_INDETERMINADA')
    return message


def collect(store,c,targets):
    with store.db() as db:
        db.execute('BEGIN IMMEDIATE')
        cursor=db.execute('SELECT seq FROM whatsapp_cursor WHERE id=1').fetchone()
        if not cursor:
            # Activate from now; do not broadcast old process history.
            seq=db.execute('SELECT COALESCE(MAX(seq),0) FROM audit').fetchone()[0]
            db.execute('INSERT INTO whatsapp_cursor VALUES(1,?)',(seq,));return
        rows=db.execute('SELECT seq,payload FROM audit WHERE seq>? ORDER BY seq LIMIT 100',(cursor[0],)).fetchall()
        for row in rows:
            event=json.loads(row['payload']);action=event.get('action')
            if action not in EVENTS:continue
            for name in targets:
                db.execute("INSERT OR IGNORE INTO whatsapp_outbox(seq,username,state,created) VALUES(?,?,'pendente',?)",(row['seq'],name,now()))
        if rows:db.execute('UPDATE whatsapp_cursor SET seq=? WHERE id=1',(rows[-1]['seq'],))


def dispatch_once(store,send=post_message):
    c=config()
    if not ready(c):return
    targets=recipients(store,c)
    collect(store,c,targets)
    with store.db() as db:
        for row in db.execute("SELECT DISTINCT username FROM whatsapp_outbox WHERE state='pendente'").fetchall():
            if row[0] not in targets:
                db.execute("UPDATE whatsapp_outbox SET state='cancelado' WHERE username=? AND state='pendente'",(row[0],))
    if not targets:return
    with store.db() as db:
        items=db.execute("SELECT seq,username FROM whatsapp_outbox WHERE state='pendente' ORDER BY seq,username LIMIT 20").fetchall()
    for item in items:
        c=config()
        if not ready(c):return
        try:enforce(store,'aviso_interno')
        except Blocked:return
        name=item['username'];phone=recipients(store,config()).get(name)
        with store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if not phone:
                db.execute("UPDATE whatsapp_outbox SET state='cancelado' WHERE seq=? AND username=? AND state='pendente'",(item['seq'],name));continue
            changed=db.execute("UPDATE whatsapp_outbox SET state='reconciliar' WHERE seq=? AND username=? AND state='pendente'",(item['seq'],name)).rowcount
            event=json.loads(db.execute('SELECT payload FROM audit WHERE seq=?',(item['seq'],)).fetchone()[0])
        if not changed:continue
        # Durable intent precedes network I/O. Crash/timeout stays reconcile.
        try:
            enforce(store,'aviso_interno')
            message_id=send(c,phone,LABELS[event['action']],'Evento '+str(item['seq']))
            state='aceito_api'
        except Blocked:
            with store.db() as db:db.execute("UPDATE whatsapp_outbox SET state='pendente' WHERE seq=? AND username=?",(item['seq'],name))
            return
        except urllib.error.HTTPError as exc:
            state='recusado' if 400<=exc.code<500 else 'reconciliar';message_id=''
        except Exception:
            state='reconciliar';message_id=''
        with store.db() as db:
            db.execute('UPDATE whatsapp_outbox SET state=?,message_id=? WHERE seq=? AND username=?',(state,message_id,item['seq'],name))
            store._audit(db,{'action':'whatsapp_interno','result':state,'recipient_key':name,'source_event':item['seq']})
