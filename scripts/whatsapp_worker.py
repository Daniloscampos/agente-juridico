"""Run one dispatcher in the protected server, alongside the dashboard."""
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.store import Store
from integrations.whatsapp import dispatch_once, status

if __name__=='__main__':
    store=Store(os.environ.get('AGENT_DB','var/operational.sqlite'))
    print('WhatsApp interno: dispatcher iniciado. Credenciais e destinatarios nao sao exibidos.')
    while True:
        try:dispatch_once(store)
        except KeyboardInterrupt:break
        except Exception:print('Configuracao ou processamento indisponivel; confira o painel e a configuracao local.')
        time.sleep(5)
