# Robô Peres & Javarotti — Aviso de publicações por WhatsApp

Versão: 08/10/2026 · Depende da etapa INTEGRA (`INTEGRACAO_VERIFICADA`)

## 1. Como funciona

```
INTEGRA → executar_integra.py → banco do painel → whatsapp_integra.py → WhatsApp Cloud API (Meta) → equipe interna
```

- O aviso só sai quando a leitura encontra publicações **novas ou alteradas**. Reler as mesmas publicações não gera outra mensagem.
- Vai **uma mensagem por leitura** para cada destinatário cadastrado. O teste começa com 1 número; depois entram os outros 3.
- **Permissões do robô:** o aviso usa a ação `aviso_interno`, que é bloqueada por pausa, por modo de erro ou por regra de revisão no painel. O robô nunca envia mensagens a clientes, porque a ação `enviar_cliente` é proibida. Só recebe quem estiver cadastrado como usuário interno, com consentimento registrado.
- **O que a mensagem traz:** apenas o que o robô leu na lista de publicações:
  - número do processo, ou mais de um quando a publicação tem 2 processos;
  - vara/órgão completo e comarca;
  - data de disponibilização;
  - quantidade de publicações novas;
  - quantidade sem processo vinculado;
  - total listado no INTEGRA.
- **O que a mensagem não traz:** o texto da publicação, prazos ou orientação jurídica.
- **Nomes de cliente e parte adversa** ficam **desligados** por padrão. Só entram com `WA_INCLUIR_PARTES=true`, por decisão do escritório.

### Exemplo de mensagem com os dados de 08/10/2026 (fictícios)

> Robô Peres & Javarotti – novas publicações no INTEGRA.
> Resumo: 6 publicacao(oes) nova(s) em 08/10/2026; 2 sem processo vinculado; total listado no INTEGRA: 6
> Processos: 1) SEM PROCESSO VINCULADO - 20ª Câmara de Direito Cível - Curitiba - disp. 08/10/2026 | 2) 0000001-00.2025.8.16.0001 - 1ª Vara Cível - Cidade A - disp. 08/10/2026 | … | 5) 0000003-00.2025.8.16.0003, 0000004-00.2025.8.16.0003 - 2ª Vara Cível - Cidade C - disp. 08/10/2026 | …
> Detalhes: painel interno do escritorio
> Mensagem automática para a equipe interna. Confira no INTEGRA antes de qualquer providência.

Quando há muitas publicações, a lista é cortada e termina com "e mais N no painel".

## 2. Checklist

**Na Meta (feito uma vez, por quem administra a conta do escritório)**
- [ ] Conta Meta Business do escritório verificada e app com o produto **WhatsApp** adicionado.
- [ ] Número empresarial cadastrado na WhatsApp Cloud API. Anote o **Phone number ID**.
- [ ] **Token permanente** de usuário do sistema, com permissão `whatsapp_business_messaging`. Ele fica **só** no `.env` do computador do robô.
- [ ] Template `aviso_publicacoes_integra` (seção 3) **aprovado**.
- [ ] Se a conta ainda estiver em modo de desenvolvimento, o número de teste precisa estar na lista de destinatários permitidos da Meta.

**No computador do robô**
- [ ] Pacote extraído e **25 testes** aprovados (seção 5.1).
- [ ] Variáveis `WA_*` no `.env` (seção 4).
- [ ] 1 destinatário de teste cadastrado (seção 5.2).
- [ ] `testar_whatsapp_integra.py` → `PRONTO_PARA_ENVIO` (seção 5.3).
- [ ] Envio de teste aceito e **conferido no celular** (seção 5.4).
- [ ] Ciclo real `executar_integra.py` mostrando `WHATSAPP=` com `aceito_api: 1` (seção 5.5).
- [ ] Só depois disso, os outros 3 números cadastrados (seção 6).

## 3. Template para aprovar na Meta

No WhatsApp Manager, vá em **Modelos de mensagem → Criar modelo** e preencha:

- **Categoria:** Utilidade
- **Nome:** `aviso_publicacoes_integra`
- **Idioma:** Português (BR)
- **Corpo:**

```
Robô Peres & Javarotti – novas publicações no INTEGRA.
Resumo: {{1}}
Processos: {{2}}
Detalhes: {{3}}
Mensagem automática para a equipe interna. Confira no INTEGRA antes de qualquer providência.
```

Exemplos para a análise da Meta (dados fictícios):

- {{1}} = `2 publicacao(oes) nova(s) em 08/10/2026; 1 sem processo vinculado; total listado no INTEGRA: 2`
- {{2}} = `1) 0000001-00.2025.8.16.0001 - 1ª Vara Cível - Curitiba - disp. 08/10/2026 | 2) SEM PROCESSO VINCULADO - 6ª Turma Recursal - Curitiba - disp. 08/10/2026`
- {{3}} = `painel interno do escritorio`

## 4. Variáveis no `.env`

Abra o `.env` com `notepad "$env:USERPROFILE\agente-juridico\.env"` e acrescente as linhas abaixo. Preencha os valores **só no seu computador** e nunca os envie no chat.

```
WA_INTEGRA_ENABLED=true
WA_TOKEN=COLE_AQUI_O_TOKEN
WA_PHONE_NUMBER_ID=COLE_AQUI_O_ID
WA_API_VERSION=v21.0
WA_TEMPLATE_PUBLICACOES=aviso_publicacoes_integra
WA_LANGUAGE=pt_BR
WA_RECIPIENTS_FILE=var/whatsapp-recipients.json
WA_INCLUIR_PARTES=false
WA_PANEL_URL=
```

- `WA_API_VERSION`: use a versão da Graph API indicada no painel da Meta.
- `WA_PANEL_URL`: deixe vazio enquanto o painel for só local (`127.0.0.1`). A mensagem dirá "painel interno do escritório". Quando houver endereço HTTPS, coloque-o aqui.

## 5. Teste com 1 número

### 5.1 Testes offline
```powershell
cd "$env:USERPROFILE\agente-juridico"
& ".\.venv\Scripts\python.exe" -m unittest tests.test_whatsapp_integra tests.test_integra_integracao -v
```
Esperado: `Ran 25 tests ... OK`.

### 5.2 Cadastrar o destinatário de teste
O destinatário precisa ser um **usuário ativo do painel**. Use o seu usuário de login do painel, por exemplo `admin`. O número vai no formato internacional, só com dígitos: `55` + DDD + número.
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\manage_whatsapp.py add admin --phone 5541999999999 --internal-consent
```
Troque `admin` pelo seu usuário do painel e o número pelo número real. Para remover: `... manage_whatsapp.py remove admin`.

### 5.3 Conferir sem enviar
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\testar_whatsapp_integra.py
```
Esperado: W1 a W4 OK, a **prévia** da mensagem e `RESULTADO_FINAL=PRONTO_PARA_ENVIO`. Nada é enviado.

### 5.4 Enviar a mensagem de teste
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\testar_whatsapp_integra.py --enviar
```
Esperado: `W5 envio` OK e `RESULTADO_FINAL=ENVIO_ACEITO`. **Confira no celular** se a mensagem chegou: "aceito pela Meta" não garante a entrega.

### 5.5 Ciclo real
```powershell
& ".\.venv\Scripts\python.exe" .\executar_integra.py
```
- Se houver publicações novas, a saída mostra `WHATSAPP={"aceito_api": 1, ...}`.
- Sem novidades, mostra `"lote": "sem novidades"` e nada é enviado.

## 6. Ampliar para as 4 pessoas
Cada pessoa precisa de usuário ativo no painel: `scripts\manage_users.py create NOME --role reader`. Depois, cadastre o número de cada uma:
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\manage_whatsapp.py add NOME --phone 55DDDNUMERO --internal-consent
```
Peça a autorização de cada pessoa antes de cadastrar. Repita a seção 5.3 para conferir os 4 nomes (os números aparecem mascarados).

## 7. Resultados e o que fazer

| Resultado | Significado | Ação |
|---|---|---|
| `aceito_api` | A Meta aceitou | Conferir no celular |
| `recusado` | Erro 4xx: token, template não aprovado, número fora da lista de teste ou limite de envio (429) | Conferir template, token e número; aguardar e rodar de novo se for limite |
| `reconciliar` | Sem resposta (timeout ou 5xx) | **Não reenviar às cegas.** Conferir no WhatsApp Manager se a mensagem saiu |
| `CONFIG_INCOMPLETA` | Falta alguma `WA_*` | Seção 4 |
| `BLOQUEADO: AGENTE_PAUSADO` | Robô pausado no painel | Retomar no painel |
| `WHATSAPP=ERRO (...)` | Falha no aviso | A leitura foi gravada normalmente; ver `logs\agente.log` |

## 8. Observações
- Se o robô estiver pausado ou a configuração incompleta, os avisos ficam **na fila** e saem quando tudo estiver liberado (podem chegar atrasados).
- Uma mesma combinação de publicações gera um único aviso.

## 9. Desligar
Coloque `WA_INTEGRA_ENABLED=false` no `.env`, ou pause o robô no painel.
