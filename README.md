# Etapa 65.1 — Consolidação local (somente leitura)

Conteúdo das Etapas 64 e 65. **Não substitui** os módulos antigos em `integrations/` e `core/`. O parser de registros preenchidos continua bloqueado. Os testes são simulados; o smoke real precisa ser executado no Windows com login manual.

## Instalação segura

Extraia o ZIP em uma pasta temporária e confira conflitos antes de copiar. A instalação só adiciona `integra/`, `orquestrador/`, `tests/`, `scripts/`, `requirements.txt`, `.gitignore`, `.env.example` e este README. Não há credenciais. `requirements.txt` pode já existir no projeto: **não o sobrescreva** sem conciliar as dependências antigas. Consulte os comandos PowerShell fornecidos na resposta.

## Smoke

`python scripts/smoke_agenda_real.py` abre Chrome separado, solicita login manual e navegação manual à Agenda, e consulta o mês local corrente. Não executa POST de cadastro nem alterações. Esperado para conta estagiária sem tarefas: `STATUS=VAZIO QUANTIDADE=0`.

## Limitações

O `hdTipoData` é configurado como modo Semana na implementação anterior, embora as datas de consulta sejam explícitas; esse comportamento exige validação real para o mês completo. Um retorno `VAZIO` só homologa o cenário vazio no período testado, não o parser de linhas nem a paginação. Para registros preenchidos, a função lança `AgendaParserNaoHomologado`.
