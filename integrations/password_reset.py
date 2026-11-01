"""Password recovery transport. No send occurs until institutional SMTP is configured."""
from email.message import EmailMessage
import os
import smtplib
import ssl
from urllib.parse import urlparse


def configured():
    names=['DASH_PUBLIC_URL','RESET_SMTP_HOST','RESET_SMTP_USER','RESET_SMTP_PASSWORD','RESET_SMTP_FROM']
    if not all(os.environ.get(n) for n in names):return False
    url=urlparse(os.environ['DASH_PUBLIC_URL'])
    return url.scheme=='https' and bool(url.hostname) and not url.username and not url.password and not url.query and not url.fragment


def send_reset(email, token):
    if not configured():raise RuntimeError('RESET_EMAIL_NOT_CONFIGURED')
    origin=os.environ['DASH_PUBLIC_URL'].rstrip('/')
    msg=EmailMessage();msg['From']=os.environ['RESET_SMTP_FROM'];msg['To']=email
    msg['Subject']='Redefinição de senha — Agente Jurídico'
    msg.set_content('Foi solicitada a redefinição da sua senha. O link abaixo expira em 30 minutos e só pode ser usado uma vez.\n\n'+origin+'/reset-password#token='+token+'\n\nSe não foi você, ignore esta mensagem. Sua senha permanece inalterada.')
    with smtplib.SMTP_SSL(os.environ['RESET_SMTP_HOST'],int(os.environ.get('RESET_SMTP_PORT','465')),timeout=20,context=ssl.create_default_context()) as smtp:
        smtp.login(os.environ['RESET_SMTP_USER'],os.environ['RESET_SMTP_PASSWORD'])
        if smtp.send_message(msg):raise RuntimeError('RESET_EMAIL_REJECTED')
