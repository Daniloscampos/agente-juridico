# Etapa 65.1 - Falhas conhecidas

## Resultado da suite completa
- 119 testes aprovados, 2 falhas e 5 subtestes aprovados.
- Os 12 testes especificos das Etapas 64 e 65 foram aprovados.
- Smoke real da Agenda: STATUS=VAZIO QUANTIDADE=0.

## Falha 1 - test_official_endpoint_and_key
- Arquivo: Atualizacao_OpenAI_ElevenLabs/tests/test_migracao_openai.py
- Erro: URL obtida https://api.groq.com/openai/v1; URL esperada https://api.openai.com/v1.
- Causa provavel: divergencia entre a configuracao atual e a expectativa do teste.

## Falha 2 - test_openai_priority
- Arquivo: Atualizacao_OpenAI_ElevenLabs/tests/test_migracao_openai.py
- Erro: resultado claude; resultado esperado ok.
- Causa provavel: prioridade de provedores diferente da esperada pelo teste.

## Decisao
- Falhas preexistentes documentadas; nao corrigidas nesta etapa.
- Nenhum provedor, credencial ou configuracao de IA foi alterado.
- Parser de agendamentos preenchidos continua pendente de homologacao.
