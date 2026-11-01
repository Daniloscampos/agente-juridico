"""Private dashboard with password login and revocable server-side sessions."""
import hmac
import os
from pathlib import Path
from fastapi import FastAPI, Depends, Request, Response, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from core.store import Store
from core.auth import Auth, SESSION_SECONDS
from core.policy import AUTO, Blocked

app = FastAPI(title='Peres e Javarotti — Agente Operacional', docs_url=None, redoc_url=None, openapi_url=None)
store = Store(os.environ.get('AGENT_DB','var/operational.sqlite'))
COOKIE = 'agent_session'

@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Pydantic errors can include submitted password/token values; do not echo them.
    return JSONResponse(status_code=422,content={'detail':'Confira os campos informados.'})



def secure_cookie():
    # HTTP is allowed only when explicitly configured for a local SSH tunnel.
    return os.environ.get('DASH_COOKIE_SECURE','true').lower() != 'false'


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response=await call_next(request)
    response.headers['Cache-Control']='no-store'
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; form-action 'self'"
    return response


def same_origin(request):
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403,'Origem de acesso invalida')


def role(request: Request):
    if secure_cookie() and request.url.scheme!='https':raise HTTPException(401,'Acesso HTTPS exigido')
    identity=Auth(store).session(request.cookies.get(COOKIE,''))
    if not identity: raise HTTPException(401,'Login exigido ou sessao expirada')
    if request.method not in {'GET','HEAD','OPTIONS'}:
        same_origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''),identity['csrf']):
            raise HTTPException(403,'Validacao da sessao exigida')
    return identity


def admin(r=Depends(role)):
    if r['role']!='admin':raise HTTPException(403,'Permissao administrativa exigida')
    return r


class Login(BaseModel):
    username: str = Field(min_length=1,max_length=100)
    password: str = Field(min_length=1,max_length=256)


@app.get('/login',response_class=HTMLResponse)
def login_page():
    return Path(__file__).with_name('login.html').read_text(encoding='utf-8')


@app.post('/api/auth/login')
def login(body:Login,request:Request,response:Response):
    same_origin(request)
    if secure_cookie() and request.url.scheme!='https':
        raise HTTPException(400,'Acesso HTTPS exigido; use configuracao local somente via tunel')
    identity,error=Auth(store).login(body.username,body.password,request.client.host if request.client else 'unknown')
    if error:
        raise HTTPException(429 if error=='limited' else 401,'Acesso recusado. Confira os dados ou tente novamente mais tarde.')
    response.set_cookie(COOKIE,identity['token'],httponly=True,secure=secure_cookie(),samesite='strict',max_age=SESSION_SECONDS,path='/')
    return {k:identity[k] for k in ('username','role','csrf')}


@app.get('/api/auth/me')
def me(r=Depends(role)):return r


@app.post('/api/auth/logout')
def logout(request:Request,response:Response,r=Depends(role)):
    Auth(store).logout(request.cookies.get(COOKIE,''),r['username'])
    response.delete_cookie(COOKIE,path='/',secure=secure_cookie(),httponly=True,samesite='strict')
    return {'status':'desconectado'}


@app.get('/',response_class=HTMLResponse)
def index(request:Request):
    if not Auth(store).session(request.cookies.get(COOKIE,'')):
        return RedirectResponse('/login',status_code=303)
    return Path(__file__).with_name('index.html').read_text(encoding='utf-8')


class Pause(BaseModel):paused:bool
class Limit(BaseModel):
    action:str
    review:bool
class Review(BaseModel):
    decision:str
    comment:str=Field(default='',max_length=2000)


@app.get('/api/state')
def state(r=Depends(role)):return store.snapshot()


@app.post('/api/pause')
def pause(body:Pause,r=Depends(admin)):
    store.set_pause(body.paused,r['username'])
    return {'control':store.control(),'note':'pausa cooperativa; acao ja enviada exige conferencia'}


@app.post('/api/limits')
def limits(body:Limit,r=Depends(admin)):
    if body.action not in AUTO:raise HTTPException(400,'Acao proibida ou desconhecida')
    store.limit(body.action,body.review,r['username'])
    return {'status':'limite_atualizado'}


@app.get('/api/audit')
def audit(r=Depends(role)):
    return {'chain_valid':store.verify(),'events':store.snapshot()['audit'],'note':'ultimos 100 eventos'}


@app.post('/api/runs/{key}/review')
def review(key:str,body:Review,r=Depends(admin)):
    try:return store.review_run(key,r['username'],body.decision,body.comment)
    except Blocked as exc:raise HTTPException(409,str(exc)) from exc


class Forgot(BaseModel):username:str=Field(min_length=1,max_length=100)
class Reset(BaseModel):
    token:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=12,max_length=256)


@app.get('/api/auth/options')
def auth_options():
    from integrations.password_reset import configured
    return {'email_recovery':configured()}


@app.post('/api/auth/forgot-password')
def forgot(body:Forgot,request:Request):
    from integrations.password_reset import configured,send_reset
    same_origin(request)
    if not configured():
        raise HTTPException(503,'Recuperacao por email ainda nao configurada. Solicite a redefinicao ao administrador.')
    if request.url.scheme!='https':raise HTTPException(400,'Acesso HTTPS exigido')
    auth=Auth(store);reset=auth.request_reset(body.username,request.client.host if request.client else 'unknown')
    if reset:
        try:send_reset(reset['email'],reset['token'])
        except Exception:
            auth.discard_reset(reset['token'])
            store.event(action='recuperacao_senha',result='erro_de_envio')
    return {'message':'Se o usuario estiver cadastrado e o envio for concluido, recebera um link por email. Confira a caixa de spam ou procure o administrador.'}


@app.get('/reset-password',response_class=HTMLResponse)
def reset_page():return Path(__file__).with_name('reset-password.html').read_text(encoding='utf-8')


@app.post('/api/auth/reset-password')
def reset_password(body:Reset,request:Request):
    same_origin(request)
    if secure_cookie() and request.url.scheme!='https':raise HTTPException(400,'Acesso HTTPS exigido')
    try:Auth(store).consume_reset(body.token,body.password)
    except ValueError as exc:raise HTTPException(400,str(exc)) from exc
    return {'message':'Senha redefinida. Entre novamente com sua nova senha.'}


@app.get('/api/whatsapp/status')
def whatsapp_status(r=Depends(role)):
    from integrations.whatsapp import status
    return status(store)


@app.get('/api/robo/resumo')
def robo_resumo(r=Depends(role)):
    """Atendente de WhatsApp (UazAPI): estado, atendimentos do dia e publicacoes - sem conteudo nem chaves."""
    from integrations.painel_robo import resumo
    return resumo(store)
