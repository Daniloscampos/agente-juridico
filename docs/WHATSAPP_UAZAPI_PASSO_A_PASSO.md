# Robô Peres & Javarotti — WhatsApp pela UazAPI (aviso automático + atendimento)

Versão: 08/10/2026 · Número: o que está conectado no painel da UazAPI (uazapi.dev)

## 1. O que o robô faz pelo WhatsApp

**A) Aviso automático:** a cada leitura do INTEGRA com publicações novas, uma mensagem para cada pessoa da equipe cadastrada. Isso vale também quando a leitura é feita pelo atendente, por exemplo num pedido `publicacoes hoje`.

**B) Atendimento:** o advogado manda um pedido, o robô consulta o INTEGRA e responde.

| O advogado envia | O robô responde |
|---|---|
| `publicacoes hoje` (ou `hoje`) | Consulta **ao vivo** no INTEGRA: total, quantas estão sem processo vinculado e, para cada publicação, número do processo, vara/órgão, comarca e data |
| `processo 0000000-00.0000.0.00.0000` | Publicações desse processo |
| `publicacoes 07/10/2026` | Publicações da data |
| `sem vinculo` | Publicações sem processo vinculado |
| `ajuda` | Lista de pedidos |

- Antes de responder pedidos de processo, data ou sem vínculo, o robô atualiza as publicações de hoje e então responde com **todas as publicações que ele já leu** do INTEGRA. A resposta informa desde quando ele tem esses dados.
- A busca **ao vivo** por outra data ou por número de processo na própria tela do INTEGRA fica para a versão 2. Para isso, os campos "Data" e "Nº Processo" precisam ser mapeados, como fizemos com o botão Pesquisar.

**Regras, que são as mesmas permissões do robô:**
- **Quem é atendido:** só números da **equipe interna cadastrada**. Números desconhecidos e grupos são **ignorados**, e a tentativa fica registrada.
- **Somente consulta.** Pedidos para protocolar, assinar, pagar, marcar publicação como lida, apagar ou enviar algo a cliente são **recusados**, com a explicação.
- **Robô pausado** (no painel ou pelo arquivo `.paused`): ele não consulta e não responde.
- **INTEGRA fora do ar:** a resposta é "Não consegui consultar… isso NÃO significa que não há publicações".
- Cada mensagem é respondida **uma única vez**.
- Há um limite de 8 pedidos por minuto para cada número.
- A auditoria do painel registra quem pediu, o tipo de pedido e o resultado, **sem o conteúdo**.

**Aviso sobre a UazAPI.** A UazAPI conecta o número como o **WhatsApp Web** e não é a API oficial da Meta. O WhatsApp pode **restringir ou banir** números usados em automação, principalmente quando há muitas mensagens ou mensagens para quem não espera recebê-las. Como o uso é **só interno** (4 pessoas da equipe), o risco é menor. Mesmo assim, use um número **exclusivo do robô** e não o número principal do escritório.

## 2. Checklist

- [ ] Número **exclusivo do robô** conectado no painel da UazAPI (QR Code), com o status **connected**.
- [ ] No painel da UazAPI, copiar o **endereço do servidor** e o **token da instância**. O token de administração (`admintoken`) **não** é usado.
- [ ] Pacote extraído e **38 testes** aprovados (seção 4.1).
- [ ] `.env` preenchido (seção 3).
- [ ] 1 número de teste cadastrado (seção 4.2).
- [ ] `testar_uazapi.py` → `CONEXAO_OK` e, com `--enviar`, `ENVIO_ACEITO`, **conferido no celular** (seção 4.3).
- [ ] Atendente ligado e respondendo `ajuda` e `publicacoes hoje` (seção 4.4).
- [ ] Aviso automático no ciclo `executar_integra.py`, com `WHATSAPP=` mostrando `aceito_api: 1` (seção 4.5).
- [ ] Os outros 3 números cadastrados (seção 5).

## 3. `.env`

Abra o arquivo com `notepad "$env:USERPROFILE\agente-juridico\.env"` e acrescente as linhas abaixo. Preencha **só no seu computador** e nunca envie o token no chat.

```
WA_PROVIDER=uazapi
WA_INTEGRA_ENABLED=true
WA_ATENDENTE_ENABLED=true
WA_RECIPIENTS_FILE=var/whatsapp-recipients.json
WA_INCLUIR_PARTES=false
UAZAPI_URL=https://SEU-SERVIDOR.uazapi.com
UAZAPI_TOKEN=COLE_AQUI_O_TOKEN_DA_INSTANCIA
```

- `UAZAPI_URL`: o endereço que aparece no painel da UazAPI. Comece com `https://` e não coloque barra no final.
- `WA_INCLUIR_PARTES=true` inclui cliente e parte adversa no aviso automático. A decisão é do escritório.

## 4. Teste com 1 número

### 4.1 Testes offline
```powershell
cd "$env:USERPROFILE\agente-juridico"
& ".\.venv\Scripts\python.exe" -m unittest tests.test_atendente tests.test_whatsapp_integra tests.test_integra_integracao -v
```
Esperado: `Ran 38 tests ... OK`.

### 4.2 Cadastrar o número de teste
O destinatário precisa ser um usuário ativo do painel. Use o seu usuário de login do painel, por exemplo `admin`. O número vai com 55 + DDD + número, só com dígitos.
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\manage_whatsapp.py add admin --phone 5541999999999 --internal-consent
```

### 4.3 Testar a conexão e o envio
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\testar_uazapi.py
& ".\.venv\Scripts\python.exe" .\scripts\testar_uazapi.py --enviar
```
Esperado: U1 a U3 OK com `CONEXAO_OK`. Depois, com `--enviar`, `ENVIO_ACEITO` e a mensagem de teste no celular.

### 4.4 Ligar o atendente
Feche qualquer Chrome antigo do robô e execute:
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\atendente_whatsapp.py
```
1. O Chrome do robô abre. Faça o login no INTEGRA.
2. Quando aparecer **"Atendente pronto"**, mande do celular cadastrado: `ajuda`, depois `publicacoes hoje`.
3. Cada pedido aparece no PowerShell como `pedido de admin: respondido`.
4. Deixe essa janela aberta durante o expediente. **Ctrl + C** encerra.

O atendente usa uma conexão de **saída** com a UazAPI, então **não é preciso abrir porta, túnel nem webhook**. O computador precisa ficar ligado e com o Chrome do robô aberto.

### 4.5 Aviso automático
Com o atendente **fechado**, já que os dois usam o mesmo Chrome do robô, execute:
```powershell
& ".\.venv\Scripts\python.exe" .\executar_integra.py
```
Se houver publicações novas: `WHATSAPP={"aceito_api": 1, ...}`.

## 5. Ampliar para as 4 pessoas
Cada pessoa precisa de usuário no painel, criado com `scripts\manage_users.py create NOME --role reader`. Depois, cadastre o número dela:
```powershell
& ".\.venv\Scripts\python.exe" .\scripts\manage_whatsapp.py add NOME --phone 55DDDNUMERO --internal-consent
```
Peça a autorização de cada pessoa. Reinicie o atendente depois de cadastrar, porque ele carrega a lista de números ao iniciar.

## 6. Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `NUMERO_DESCONECTADO` | Reconectar o número pelo QR Code no painel da UazAPI |
| `UAZAPI_URL invalida` / `UAZAPI_TOKEN vazio` | Revisar o `.env` (seção 3) |
| `UAZAPI INACESSIVEL` | Conferir a internet e o endereço do servidor |
| O robô não responde | Conferir se o número está cadastrado, se não é grupo e se o robô não está pausado no painel |
| "Não consegui consultar o INTEGRA" | Ver a janela do Chrome do robô (login expirado?), entrar de novo e repetir o pedido |
| O número do remetente aparece como `@lid` | Algumas contas escondem o número. Envie do celular cadastrado e mande uma imagem do PowerShell para ajuste |

## 7. Desligar
`WA_ATENDENTE_ENABLED=false` e/ou `WA_INTEGRA_ENABLED=false` no `.env`, ou pausar o robô no painel.
