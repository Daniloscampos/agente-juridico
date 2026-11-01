# Robô Peres & Javarotti — Etapa final: integração com o INTEGRA (somente leitura)

Versão do pacote: 08/10/2026 · Projeto: `C:\Users\danil\agente-juridico` · Python 3.12+ · Selenium 4.25

## 1. O que esta etapa entrega

| Item | Arquivo | Função |
|---|---|---|
| Configuração | `core/config.py`, `.env.example` | Novas chaves `INTEGRA_LOGIN_URL`, `INTEGRA_LOGIN_MODE`, `INTEGRA_PROFILE_DIR`, `AGENT_DB` etc. |
| Conector | `integrations/integra.py` | Login (`txtUsuario`/`txtSenha`), confirmação da área interna, abertura de Publicações e leitura da listagem. **Toda escrita bloqueada.** |
| Leitor da listagem | `integrations/integra_parser.py` | Interpreta a resposta de `publicacoesListar.asp` (layout validado em 08/10/2026). |
| Gravação | `integrations/integra_publicacoes.py` | Tabela `integra_publicacoes` no banco do painel; sem duplicar; auditoria só com contagens. |
| Execução | `executar_integra.py` | Ciclo de leitura (ao vivo ou a partir de um HTML salvo). |
| Teste de integração | `scripts/testar_integracao_integra.py` | Etapas T1–T8 com relatório em `saida\`. |
| Testes offline | `tests/test_integra_integracao.py` + `tests/fixtures/` | 15 testes, sem rede e com dados fictícios. |
| Próxima etapa | `integrations/whatsapp_integra.py` | Estrutura do aviso por WhatsApp, **desativada**. |

O robô **não**: abre publicações (`clickVisualizar` pode marcar como lida), escreve observações, conclui tarefas, protocola, assina, paga, usa certificado do advogado ou envia mensagens.

## 2. Checklist final de configuração

Marque cada item antes de considerar a etapa concluída.

**Segurança (fazer primeiro)**
- [ ] Revogar no Google Cloud a chave da *service account* que foi anexada no chat e gerar uma nova em `credentials\`.
- [ ] Confirmar que `.env`, `credentials\`, `.browser\` e `var\` não estão no GitHub (`.gitignore`).
- [ ] Definir a conta do robô no INTEGRA: preferir **conta técnica própria** (Administração → Usuários → +) com permissão mínima. Enquanto não existir, usar `INTEGRA_LOGIN_MODE=manual`.

**Instalação**
- [ ] Backup de `core\config.py`, `integrations\integra.py` e `.env` feito (passo 3.1).
- [ ] Pacote extraído sobre a pasta do projeto (passo 3.2).
- [ ] `.env` revisado com as chaves da seção INTEGRA do `.env.example` (passo 3.3).
- [ ] 15 testes offline aprovados (passo 4.1).

**Controles do robô**
- [ ] Arquivo `.paused` removido **e** robô retomado no painel (o painel nasce pausado).
- [ ] Painel aberto em `http://127.0.0.1:8000` para acompanhar a auditoria.

**Integração ao vivo**
- [ ] T5 — login confirmado (Clientes, Processos e Agenda visíveis).
- [ ] T6 — listagem de Publicações lida.
- [ ] T7 — rodapé "Exibindo N de M" igual às linhas lidas.
- [ ] Contagem conferida manualmente na tela do INTEGRA (ex.: 6 publicações em 08/10/2026).
- [ ] T8 — gravação idempotente (rodar com `--gravar`).
- [ ] Publicações sem processo aparecem como `vinculo_pendente`; publicação com 2 processos preserva os 2.

**Não fazer nesta etapa**
- [ ] `main.py` **não** foi executado (agora ele para sozinho: `AGENDA_INTEGRA_NAO_MAPEADA`).
- [ ] WhatsApp continua com `WA_ENABLED=false` (dispatcher ainda não configurado).

## 3. Instalação (PowerShell)

### 3.1 Backup
```powershell
cd "$env:USERPROFILE\agente-juridico"
$bk = "backup_integra_$(Get-Date -Format yyyyMMdd_HHmmss)"
New-Item -ItemType Directory $bk | Out-Null
Copy-Item .\core\config.py, .\integrations\integra.py $bk
if (Test-Path .\.env) { Copy-Item .\.env "$bk\.env" }
"Backup em $bk"
```

### 3.2 Extrair o pacote
Baixe `Integracao_INTEGRA_Etapa_Final.zip` para **Downloads** e execute:
```powershell
Expand-Archive "$env:USERPROFILE\Downloads\Integracao_INTEGRA_Etapa_Final.zip" -DestinationPath "$env:USERPROFILE\agente-juridico" -Force
```
Se o Windows salvou o download como `...(1).zip`, ajuste o nome.

### 3.3 Ajustar o `.env`
Abra o `.env` no VS Code (`code .env`) e acrescente as linhas da seção INTEGRA do `.env.example`. Valores recomendados:
```
INTEGRA_LOGIN_URL=https://www.integra.adv.br/login-integra.asp
INTEGRA_LOGIN_MODE=manual
INTEGRA_PROFILE_DIR=./.browser/integra
AGENT_DB=var/operational.sqlite
```
Use `INTEGRA_LOGIN_MODE=auto` **somente** com a conta técnica do robô, preenchendo `INTEGRA_USER` e `INTEGRA_PASS` apenas no seu computador. Nunca envie esses valores no chat.

## 4. Testes

### 4.1 Testes offline (sem abrir o INTEGRA)
```powershell
cd "$env:USERPROFILE\agente-juridico"
& ".\.venv\Scripts\python.exe" -m unittest tests.test_integra_integracao -v
& ".\.venv\Scripts\python.exe" .\scripts\testar_integracao_integra.py --somente-offline
```
Esperado: `Ran 15 tests ... OK` e `RESULTADO_FINAL=OFFLINE_VERIFICADO`. Nesta fase a linha `[FALHA] T3 pausas liberadas` é normal (as pausas só são liberadas no passo 4.2) e não impede o resultado offline.

### 4.2 Liberar as pausas
1. No painel (`http://127.0.0.1:8000`), clique em **Retomar** (perfil admin).
2. No PowerShell:
```powershell
& ".\.venv\Scripts\python.exe" -c "from core import control; control.retomar(); print(control.status())"
```
Deve imprimir `operando`.

### 4.3 Teste de integração ao vivo
Feche janelas antigas do Chrome abertas pelo robô e execute:
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\testar_integracao_integra.py
```
- No modo `manual`, faça o login na janela do Chrome que abrir (até 5 min). O robô continua sozinho depois que os menus aparecerem.
- Se surgir o aviso sobre o novo filtro, feche-o.
- Esperado: `RESULTADO_FINAL=INTEGRACAO_VERIFICADA`.

Depois, para gravar no banco do painel:
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\testar_integracao_integra.py --gravar
```

### 4.4 Execução do ciclo
```powershell
& ".\.venv\Scripts\python.exe" .\executar_integra.py
```
O resumo aparece no terminal e o relatório completo fica em `saida\integra_publicacoes_AAAAMMDD_HHMMSS.json` (contém nomes de partes — uso interno).

Para reprocessar uma resposta salva no DevTools (sem abrir o INTEGRA):
```powershell
& ".\.venv\Scripts\python.exe" .\executar_integra.py --html .\publicacoes_integra.txt --sem-gravar
```

## 5. Códigos de resultado

| Mensagem | Significado | O que fazer |
|---|---|---|
| `RESULTADO=OK` / `INTEGRACAO_VERIFICADA` | Leitura completa e conferida | Nada |
| `RESULTADO=PARCIAL` | Rodapé diferente das linhas (paginação?) | Conferir na tela; reduzir o período |
| `BLOQUEADO (AGENTE_PAUSADO...)` | Uma das pausas está ativa | Passo 4.2 |
| `CHROME_NAO_INICIOU` | Perfil do robô já aberto (erro do `erro.txt`) | Fechar o Chrome do robô ou trocar `INTEGRA_PROFILE_DIR` |
| `LOGIN_NAO_CONFIRMADO` | Login não concluído no prazo | Repetir; conferir se os menus aparecem |
| `SESSAO_EXPIRADA` | "Faça o login novamente" | Repetir o login |
| `MENU_PUBLICACOES_NAO_ENCONTRADO` | Menu diferente nesse perfil | Preencher `INTEGRA_PUBLICACOES_URL` com o endereço da tela |
| `LISTAGEM_NAO_CARREGOU` | Pesquisa sem resposta | **Não significa zero publicações.** Conferir manualmente |
| `LAYOUT_INESPERADO` | O INTEGRA mudou o HTML | Salvar o Response de `publicacoesListar.asp` e enviar para ajuste |
| `CLIQUE_PESQUISAR_BLOQUEADO` / `ERRO_NAVEGADOR:...` | Aviso/modal na frente do botão ou falha do Chrome | Fechar o aviso manualmente e repetir. **Não significa zero publicações** |
| `RESULTADO_FINAL=BLOQUEADO_POR_PAUSA` | Teste ao vivo com pausa ativa (T3) | Passo 4.2 |
| `RESULTADO_FINAL=INTEGRACAO_PARCIAL` | T7 (rodapé) ou T8 falhou | Conferir na tela; ver o relatório em `saida\` |
| `RESULTADO_FINAL=INTEGRA_INDISPONIVEL` / `CONFIGURACAO_INVALIDA` | Acesso falhou (T5/T6) / `.env` ou modo de login inválido (T2) | Ver o detalhe da linha `[FALHA]` |

## 6. Reverter
```powershell
cd "$env:USERPROFILE\agente-juridico"
Copy-Item .\backup_integra_*\config.py .\core\config.py -Force
Copy-Item .\backup_integra_*\integra.py .\integrations\integra.py -Force
```
Os arquivos novos podem permanecer; nada os executa automaticamente.

## 7. Pendências conhecidas
1. **`clickVisualizar`** — confirmar se marca a publicação como lida antes de qualquer leitura do texto integral.
2. **Agenda/tarefas do INTEGRA** — 0 pendências na conta atual; leitura e retorno de tarefas continuam bloqueados até o mapeamento.
3. **Período e paginação** — o robô usa o filtro padrão da tela (dia atual, critério "Inclusão no INTEGRA"). Períodos com mais de uma página exigem ajuste.
4. **`main.py`** — corrigir antes de usar: seleção de tarefa, estado "aguardando revisão", data fixa e nome do advogado.
5. **Conta técnica** — confirmar com o suporte PROMAD se é permitida para automação.

## 8. Próxima etapa (aguardando autorização): WhatsApp
Estrutura em `integrations/whatsapp_integra.py`, desativada (`ETAPA_AUTORIZADA = False`). Ao ativar: evento próprio `aviso_integra_publicacoes` no dispatcher existente (API oficial da Meta, template aprovado, destinatários internos), mensagem apenas com contagens e link do painel. Detalhes em `docs/WHATSAPP_INTERNO.md`.
