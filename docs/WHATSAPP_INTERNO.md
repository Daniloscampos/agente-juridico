# WhatsApp interno — configuração e homologação

Implementado: dispatcher para eventos futuros da auditoria, fila persistente por evento/usuário, resumo de estado no painel e cadastro de destinatários internos. Envio exclusivamente via template da API oficial da Meta. O servidor, número e credenciais não foram configurados nem houve envio real nesta entrega.

## Informações enviadas

Pausa, retomada, mudança de regra, revisão, erro crítico, bloqueio/falha de tarefa e mudança de estado da preparação. Mensagem: tipo do evento, referência “Evento N” e endereço HTTPS do painel. Não envia anexos, conteúdo do processo, CPF, senha, token ou links públicos de documentos. O usuário consulta a informação completa no painel autenticado. Cada destinatário recebe os mesmos avisos operacionais; configure apenas a equipe que está autorizada a acompanhar toda a operação. Clientes permanecem fora do canal.

## Configurar no servidor protegido

1. Criar/configurar número empresarial e acesso à WhatsApp Cloud API na conta do escritório. Usar versão Graph API suportada pela conta e credencial com permissão de envio. Não enviar token pelo chat, salvar no GitHub ou inserir na interface.
2. Criar e aprovar um template em português com três parâmetros de texto no corpo. Exemplo: “Atualização do agente jurídico: {{1}}. Referência: {{2}}. Consulte o painel interno: {{3}}.” A aprovação e a categoria dependem da Meta.
3. Configurar variáveis de ambiente tanto no processo do painel quanto no dispatcher: WA_ENABLED=true, WA_TOKEN, WA_PHONE_NUMBER_ID, WA_API_VERSION (formato vNN.N), WA_TEMPLATE, WA_LANGUAGE=pt_BR, WA_PANEL_URL (HTTPS acessível pela equipe), WA_RECIPIENTS_FILE (caminho protegido; padrão var/whatsapp-recipients.json). AGENT_DB deve ser o mesmo nos dois processos. Defina segredos no ambiente/gerenciador de segredos; o programa não carrega um .env automaticamente.
4. Cadastrar somente usuário interno ativo do painel, após sua autorização. No diretório original, executar: `.venv\Scripts\python.exe scripts\manage_whatsapp.py add USUARIO --phone NUMERO_INTERNACIONAL --internal-consent`. Substituir os marcadores. Remover: `.venv\Scripts\python.exe scripts\manage_whatsapp.py remove USUARIO`.
5. Executar `.venv\Scripts\python.exe scripts\whatsapp_worker.py` em outro terminal, mantendo o painel ativo. Em VPS, instalar serviço separado para esse processo. Nenhum serviço de produção foi instalado por esta alteração.
6. O primeiro ciclo marca o início a partir do último evento existente; não dispara histórico. Novos eventos geram avisos. A pausa e a regra de intervenção para aviso_interno mantêm mensagens pendentes até liberação. Atenção: enquanto pausado, o aviso de pausa também fica pendente.

## Conferir antes da ativação

- Usar usuários e número de homologação autorizados; verificar modelo aprovado e acesso real ao painel.
- Gerar um evento novo, verificar uma mensagem e seu identificador aceito pela API. Repetir processamento: não duplicar.
- Pausar e exigir intervenção para aviso interno: nenhuma nova mensagem enviada; liberar e conferir pendentes.
- Remover/desativar usuário antes do envio: cancelar seu pendente.
- Reiniciar dispatcher: preservar fila e não reenviar “aceito_api”. Interrupção após reserva fica “reconciliar”.
- Erro 4xx: “recusado”; timeout/5xx/resposta inválida: “reconciliar”. Nenhum desses é repetido automaticamente; conferir no provedor antes de qualquer intervenção manual na fila.
- “Aceito pela API” não significa entrega ou leitura. Webhook de entrega/leitura e interface de reconciliação são evolução futura, não implementados aqui.
- Resumo no painel informa configuração e contagens; não comprova dispatcher em execução, template aprovado ou integração homologada.

Contatos ficam no arquivo local protegido, fora do repositório e do pacote. Cadastro por script deve ser realizado pelo administrador do servidor. A automação não recebe comandos pelo WhatsApp nesta versão e não permite protocolos, assinaturas, pagamentos ou mensagens para clientes.

Referência técnica: documentação oficial da Meta no Postman, WhatsApp Cloud API — messages/template: https://www.postman.com/meta/whatsapp-business-platform/documentation/wlk6lh4/whatsapp-cloud-api
