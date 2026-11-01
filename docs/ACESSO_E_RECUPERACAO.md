# Login e recuperação de senha — 03/10/2026

## Implementado
- Tela `/login`, usuário/senha, contas `admin` e `reader`, botão Sair e identificação do usuário no dashboard e auditoria.
- PBKDF2-HMAC-SHA256 com 600.000 iterações e salt aleatório por senha. Não há senha padrão, cadastro público ou senha em texto puro no banco.
- Sessão aleatória mantida no servidor; somente hash do identificador no banco; cookie HttpOnly, Secure por padrão e SameSite=Strict. Logout e redefinição revogam sessões.
- Expiração absoluta em 8 horas e inatividade de 30 minutos (polling ativo do dashboard conta como atividade).
- Limite de 5 tentativas de login por usuário/IP em janela de 15 minutos; resposta genérica. Atrás de proxy, o limite por IP depende da configuração de encaminhamento confiável; não confiar indiscriminadamente em proxies.
- Proteção CSRF para ações autenticadas e validação de Origin no login/recuperação.
- Recuperação por e-mail, token aleatório com validade de 30 minutos e uso único; hash do token no banco. Link usa fragmento e não envia o token em query aos logs de acesso.
- SMTP sem configuração retorna mensagem explícita para procurar administrador. Não afirmar que houve envio.

## Criar o primeiro acesso
No servidor protegido, como usuário de serviço, em `/opt/agente-juridico`:
```bash
export AGENT_DB=/var/lib/agente-juridico/operational.sqlite
.venv/bin/python scripts/manage_users.py create danilo --role admin --email EMAIL_DO_USUARIO
```
Substituir apenas o e-mail pelo endereço confirmado do titular. A senha é digitada e confirmada sem eco no terminal. Mínimo 12 caracteres; utilizar senha longa e exclusiva. Não passar senha como argumento, em Git, chat ou arquivos do projeto. Criar outras contas com `--role reader` para consulta e `admin` somente para pessoas que podem controlar o robô. Os perfis são do escritório único da POC; não existe isolamento SaaS por cliente nesta entrega.

## Recuperação assistida, sem e-mail
```bash
export AGENT_DB=/var/lib/agente-juridico/operational.sqlite
.venv/bin/python scripts/manage_users.py reset-password danilo
```
Confirmar a identidade do solicitante antes da operação. Todas as sessões e links de recuperação desse usuário são invalidados.

## Habilitar “Esqueci minha senha” por e-mail
Configurar diretamente em `/etc/agente-juridico/dashboard.env`, com acesso restrito (0600), sem versionar:
- `DASH_PUBLIC_URL`: endereço HTTPS real do dashboard, sem query ou fragmento.
- `RESET_SMTP_HOST`: host institucional de e-mail.
- `RESET_SMTP_PORT`: porta de SMTP TLS implícito, padrão 465.
- `RESET_SMTP_USER`, `RESET_SMTP_PASSWORD`: credenciais exclusivas para o serviço.
- `RESET_SMTP_FROM`: remetente institucional autorizado.
- `DASH_COOKIE_SECURE=true` para produção HTTPS.

Reiniciar o serviço após configurar. O usuário precisa ter e-mail confirmado no cadastro criado pelo administrador. O serviço usa SMTP SSL com validação de certificado. Caso o provedor exija STARTTLS, OAuth ou outra modalidade, o transporte deve ser adaptado antes da ativação.

Fluxo: informar usuário → clicar Esqueci minha senha → receber link no endereço cadastrado → definir nova senha → fazer login novamente. Não há alteração do e-mail por usuário anônimo. Não há envio real testado nesta revisão; transporte de recuperação foi simulado nos testes.

## Instalação e acesso
Seguir `INSTALACAO_E_HOMOLOGACAO.md`. O serviço permanece em 127.0.0.1:8080. Para acesso remoto, configurar proxy HTTPS institucional ou túnel SSH; nenhuma publicação foi feita nesta tarefa. Atrás de proxy HTTPS, transmitir esquema/host originais e confiar somente no proxy local autorizado. Nunca desativar Secure para acesso público HTTP.

A opção `DASH_COOKIE_SECURE=false` é somente para acesso local pelo túnel SSH. Os antigos `DASH_ADMIN_TOKEN` e `DASH_READ_TOKEN` não liberam acesso.

## Testes
45 testes passaram no ambiente local: senha incorreta, bloqueio de tentativas, hashing, cookie, CSRF, autorização por papel, logout, expiração de sessão, recuperação genérica, token expirado/usado, falha SMTP e revogação por redefinição; além dos testes de workflow já existentes. O frontend foi conferido por leitura e testes das rotas; não houve validação visual via navegador (restrição de acesso local).

## Pendências antes do acesso real
Instalar/atualizar na VPS, criar conta pelo terminal, cadastrar e-mail, configurar endereço HTTPS e SMTP, testar recuperação com o titular autorizado. Não houve instalação no servidor do escritório, criação de conta real ou envio de e-mail nesta tarefa. O INTEGRA permanece aguardando conta técnica separada.
