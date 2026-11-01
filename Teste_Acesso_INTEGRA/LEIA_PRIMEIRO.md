# Teste de acesso ao INTEGRA — Peres e Javarotti

Este pacote é uma etapa de diagnóstico local, não uma integração completa.
Não substitui main.py, integrations/integra.py, .env nem o painel.
Não consulta processos, lê tarefas, gera guias, envia arquivos ou registra retornos.

## Instalação e execução

1. Extraia este ZIP em uma pasta temporária.
2. Copie apenas testar_integra.py para C:\Users\danil\agente-juridico.
3. Use uma conta autorizada do agente conforme as restrições do MVP.
4. Confira no painel se o agente está pausado. O teste respeita a pausa; não inicie main.py nem outros trabalhadores enquanto testa.
5. Em outro PowerShell, execute:

```powershell
cd "$env:USERPROFILE\agente-juridico"
& ".\.venv\Scripts\python.exe" ".\testar_integra.py"
```

6. Um Chrome separado abrirá a página oficial. Faça o login manualmente nele, incluindo qualquer confirmação solicitada pelo site. O teste não lê .env nem preenche senhas.
7. Aguarde a mensagem no terminal. O navegador fecha ao terminar. Compartilhe somente a mensagem de status, sem senha.

O Selenium 4.25.0 informado no requirements.txt é necessário; se já instalado, não há reinstalação. É necessário Chrome instalado e acesso à rede para o Selenium localizar/obter o driver compatível. Nenhum teste real de compatibilidade Chrome/Windows foi realizado neste ambiente.

## Interpretação

- ACESSO_VERIFICADO: origem HTTPS correta, caminho interno /moderno/, menus Clientes/Processos/Agenda e ausência de campo de senha visível em duas leituras. Não comprova permissão de todas as funções, agenda legível ou processamento do robô.
- NAO_VERIFICADO: pode ser mudança da interface, rede, navegador, pausa ou tempo insuficiente. Não significa que a senha esteja errada.
- CANCELADO: operador interrompeu o teste com Ctrl+C.

Relatório mínimo em saida/teste_integra_*.json. Não registra nome de usuário, processos, texto da página, credenciais, cookies ou URL da sessão.
O perfil .browser/teste-integra mantém cookies localmente: não o compartilhe, não o envie ao GitHub nem inclua em ZIPs. Não usa o perfil de produção do conector.

## Pendências comprovadas no conector enviado

- Os nomes usuario/senha divergem de txtUsuario/txtSenha observados na página de login.
- As rotas agenda e tarefa/{id} e seletores table#agenda, #observacao e #concluir-tarefa são TODOs, sem validação.
- Exceções de login não devem ser interpretadas como sessão ativa; falha de agenda não deve virar uma lista vazia como se a leitura tivesse funcionado.
- main.py pega a primeira tarefa sem validar responsabilidade/tipo, verifica pausa somente no começo e informa CONCLUIDO enquanto aguarda revisão.
- A composição completa depende ainda dos módulos locais de banco, controle e geração. Não foram enviados seus conteúdos para validação.

## Validação deste pacote

Seis testes unitários com oito entradas negativas/positivas de origem e evidências, além do bloqueio por pausa; não acessam INTEGRA nem usam credenciais.
Para executar os testes na pasta extraída: python -m unittest -v test_testar_integra.py.
A conexão real deve ser verificada no computador do operador. Após isso, a próxima etapa é mapear a agenda em leitura e validar o filtro de tarefas do agente antes de habilitar escrita.
