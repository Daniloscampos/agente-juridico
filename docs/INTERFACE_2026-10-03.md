# Interface de supervisão — 03/10/2026

## Atualização
- Painel com menu lateral, indicadores separados, áreas de operação, entregas, limites e auditoria.
- Layout responsivo, navegação por teclado, campos com rótulos e mensagens de confirmação/erro.
- Tela de login e recuperação com a identidade visual do escritório.
- Busca local nos últimos 100 eventos carregados e seleção de execução na lista para revisão.
- O estado do painel distingue conexão com a API de habilitação das etapas; não indica saúde do worker sem evidência.
- A seleção de limites aplica uma nova regra, sem representar leitura da configuração previamente salva.

## Validação
45 testes locais existentes aprovados. JavaScript das três telas com sintaxe validada. Verificações adicionais em DOM simulado confirmaram indicadores, busca, seleção de execução, pausa/retomada, envio de CSRF, bloqueio do perfil leitor, falha de conexão e exibição segura de conteúdo. A prévia interativa também foi executada nesse ambiente simulado. As proteções e endpoints de autenticação, sessões, CSRF, papéis e revisão permanecem no backend existente.

Não houve homologação visual em navegador neste ambiente: o Chromium não pôde ser instalado. A prévia em conversa usa dados fictícios e simula ações, sem chamadas aos sistemas reais. Conferir as três telas em navegador desktop e móvel na homologação da instalação.

Não foi realizada instalação na VPS nem conexão real ao INTEGRA, TJPR, Drive ou SMTP nesta atualização de interface.
