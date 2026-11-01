# Robô Peres & Javarotti: IA no WhatsApp (texto, áudio e imagem)

> **Novo — provedores gratuitos.** Dê dois cliques em `CONFIGURAR_IA.bat` e escolha uma opção:
>
> | Opção | Custo | Onde roda | Lê texto e áudio | Lê PDF | Lê fotos |
> |---|---|---|---|---|---|
> | 1) **Groq** | grátis, com limite diário | nuvem | sim | sim, se o PDF tiver texto | não |
> | 2) **Ollama** | grátis | **neste computador** (sigilo total) | sim | sim, se o PDF tiver texto | só com modelo de visão |
> | 3) **Claude** | pago (créditos da API) | nuvem | sim | sim | sim |
>
> - **Groq:** crie a chave em console.groq.com → API Keys. Ela começa com `gsk_`.
> - **Ollama:** instale pelo ollama.com/download e baixe um modelo no PowerShell com `ollama pull qwen2.5:7b`. Precisa de PC com **16 GB de RAM** ou mais.
> - **Para ler PDFs com Groq ou Ollama**, instale uma vez: `.\.venv\Scripts\python.exe -m pip install pypdf`.
>
> A persona do **Assistente Jurídico Virtual** fica em `integrations\ia_persona.py` e vale para os três provedores.

Versão: 09/10/2026 · Somente para a **equipe interna** · IA: Claude (Anthropic)

## 1. O que muda

| O advogado envia | O robô faz |
|---|---|
| Texto livre ("o que saiu hoje da 2ª Vara Cível?") | O Claude entende o pedido, consulta o INTEGRA pelas ferramentas do robô e responde |
| **Áudio** | Transcreve **no próprio computador** (Whisper), mostra `🎙️ Entendi: "..."` e responde em **texto + nota de voz** |
| **Foto/print** (intimação, tela, documento) | O Claude lê a imagem, extrai processo, vara e datas e cruza com o INTEGRA |
| Os pedidos fixos (`publicacoes hoje`, `processo ...`, `sem vinculo`, `publicacoes DD/MM/AAAA`) | Continuam com resposta direta, exata e sem custo de IA |

```
Áudio/Texto/Imagem (WhatsApp, equipe interna)
   │  UazAPI (SSE + busca de reserva a cada 10 s)
   ▼
Filtros fixos do robô: número cadastrado · pausa · 1 resposta por mensagem · 8 pedidos/min
   │  áudio → transcrição LOCAL (faster-whisper)
   ▼
Pedido proibido? (protocolar, assinar, pagar, marcar lida, apagar, cliente) → RECUSA (não passa pela IA)
   │
   ├─ pedido fixo → consulta direta ao INTEGRA/base do robô
   └─ pedido livre ou imagem → Claude + 4 ferramentas de CONSULTA (sem nenhuma de escrita)
   ▼
Resposta em texto (+ voz pt-BR do Windows se o pedido foi áudio) · auditoria sem conteúdo
```

**Regras mantidas:**

- Só a equipe interna é atendida.
- O robô continua **somente leitura**.
- Pedidos proibidos são recusados **antes** da IA.
- Robô pausado não responde.
- Falha do INTEGRA nunca vira "zero publicações".
- O nome das partes só vai para a IA com `WA_INCLUIR_PARTES=true`.

**Privacidade (LGPD):**

- **Com a ElevenLabs**, o áudio recebido e o texto falado vão para a ElevenLabs. **Na opção local**, o áudio não sai do computador.
- O **texto do pedido**, a **imagem** e os **dados das publicações consultadas** são enviados à API da Anthropic para gerar a resposta.
- Registre isso na política interna do escritório.

## 2. Instalação (uma vez)

Rode cada comando separado, no PowerShell, dentro da pasta agente-juridico.

**1. Voz e transcrição.** Escolha uma das opções:

- **A) ElevenLabs (recomendado):** voz natural e transcrição sem instalar nada. O áudio vai para a ElevenLabs. Crie a chave em **elevenlabs.io → Developers → API Keys**, com permissão para *Text to Speech*, *Speech to Text* e *Voices*, e rode:
  ```
  .\.venv\Scripts\python.exe .\scripts\configurar_elevenlabs.py
  ```
  O script lista as vozes da conta, você escolhe uma e ele gera `saida\teste_voz_elevenlabs.mp3` para você ouvir. Esperado: `RESULTADO=ELEVENLABS_CONFIGURADA`.
- **B) Local:** o áudio não sai do computador, mas a voz é a robótica do Windows. Instale com:
  ```
  .\.venv\Scripts\python.exe -m pip install faster-whisper
  ```

**2. Chave do Claude:**

- Acesse **console.anthropic.com**, entre em **Settings → API Keys → Create Key** e copie a chave.
- A conta precisa ter **créditos** em Billing.
- **Não envie a chave no chat.**

**3. Ligar a IA.** Cole a chave quando o script pedir; ela não aparece na tela.
```
.\.venv\Scripts\python.exe .\scripts\configurar_ia.py
```
Esperado: `RESULTADO=IA_CONFIGURADA`.

**4. Voz pt-BR do Windows** (para responder áudio com áudio): vá em **Configurações → Hora e idioma → Fala** e confira se há uma voz **Português (Brasil)**. Se não houver, adicione.

**5. Testes offline:**
```
.\.venv\Scripts\python.exe -m unittest discover -s tests -t .
```
Esperado: `Ran 89 tests ... OK`.

## 3. Ligar e testar

1. Feche o atendente antigo e o Chrome. Dê dois cliques em **INICIAR_ATENDENTE.bat** e faça o login no INTEGRA.
2. Na abertura, confira estas linhas:
   - `IA: Claude ativo (...)`
   - `Audio: transcricao ativa - ElevenLabs (scribe_v2)`, ou `local (Whisper 'small')`
   - `Voz: respostas a audios tambem em audio (ElevenLabs ...)`
3. Se escolheu a opção local, na **primeira vez** o modelo de áudio (~500 MB) é baixado. Espere aparecer `Audio: modelo de transcricao pronto.`
4. Do celular cadastrado, mande:
   - um **texto livre**, por exemplo: "tem alguma publicação de hoje sem processo vinculado?";
   - um **áudio**: "quais as publicações de hoje?". O esperado é o texto com `🎙️ Entendi:` e depois uma nota de voz;
   - uma **foto** de uma intimação com número de processo;
   - um pedido proibido, como "protocola a petição". Ele precisa ser **recusado**.

## 4. Tom das mensagens e forma de tratamento

- O robô escreve em português **formal, cordial e natural**. Cumprimenta pelo nome e conforme o horário (Bom dia/Boa tarde/Boa noite) só na primeira mensagem da conversa, ou depois de 30 minutos sem conversa.
- Erros técnicos são explicados em linguagem simples, sem códigos.
- Para definir como cada pessoa é chamada:
  ```
  .\.venv\Scripts\python.exe .\scripts\definir_tratamento.py danilo "Dr. Danilo"
  ```
  Use `--listar` para conferir os tratamentos. Depois, reinicie o atendente.
- Se o Chrome do robô for fechado, o atendente reabre o navegador sozinho. Se o INTEGRA pedir login de novo, faça o login nessa janela.

## 5. Ajustes (.env)

| Variável | Padrão | Para quê |
|---|---|---|
| `WA_IA_ENABLED` | false | Liga ou desliga a IA. Desligada, o robô volta aos pedidos fixos |
| `IA_MODELO` | claude-sonnet-5-5 | Modelo do Claude (o `claude-haiku-5-5` é mais barato e o `claude-opus-5-5` é mais forte) |
| `WA_WHISPER_MODELO` | small | `base` é mais rápido e `medium` é mais preciso e mais lento |
| `WA_RESPOSTA_VOZ` | true | Com `false`, a resposta a áudio vem só em texto |
| `VOZ_PROVEDOR` | (auto) | `elevenlabs` ou `windows` |
| `TRANSCRICAO_PROVEDOR` | (auto) | `elevenlabs` ou `local` |
| `ELEVENLABS_MODELO_VOZ` | eleven_multilingual_v2 | Também aceita `eleven_v4` (mais natural) ou `eleven_flash_v2_5` (mais barato e rápido) |

## 6. Problemas comuns

| Mensagem | O que fazer |
|---|---|
| `IA: DESLIGADA - ANTHROPIC_API_KEY vazia` | Rodar `configurar_ia.py` |
| `IA: indisponivel (HTTP 401)` | A chave está errada ou foi revogada: gerar outra |
| `IA: indisponivel (HTTP 400/402)` | Falta crédito na conta da Anthropic |
| `Audio: desligado` | Instalar o `faster-whisper` (seção 2) |
| "Estou terminando de preparar a transcrição" | O modelo ainda está sendo baixado. Aguarde |
| `Voz: indisponivel` | Rodar `configurar_elevenlabs.py` ou adicionar a voz Português (Brasil) no Windows |
| `HTTP 401 quota_exceeded` (ElevenLabs) | Os créditos da ElevenLabs acabaram |
| "Não consegui usar a IA agora" | Internet ou API fora do ar. Os pedidos fixos continuam funcionando |


## Orquestrador: vários provedores ao mesmo tempo

Rode `CONFIGURAR_IA.bat` uma vez para cada provedor (1 Groq, 2 Ollama, 3 Claude). O robô usa sempre
na ordem **Claude > Groq > Ollama** (só os configurados) e troca sozinho, na mesma mensagem, se um falhar:

| Falha | Pausa do provedor |
|---|---|
| Sem crédito / chave recusada | 1 hora |
| Limite de uso (429) | 2 minutos |
| Fora do ar / tempo esgotado | 1 minuto |

- Ao iniciar o atendente aparece: `IA: ordem de uso -> claude > groq > ollama`.
- No painel (porta 8000), em "Robô no WhatsApp", cada provedor aparece com ✓ ou "em pausa, volta em X min".
- Quem conversa nunca vê nomes de modelos nem percebe a troca de provedor (sem frase de transição).
- Diretriz humanizada: sem "Entendi: ...", sem "Recebi sua mensagem", sem "modo de contingência",
  sem listas de comandos e sem repetir a mesma resposta; limitações só quando pedirem algo assim.
- Com o Ollama as respostas são curtas; para análises longas ele avisa com empatia e oferece o que já pode adiantar.
- Áudio: ElevenLabs > Groq Whisper > transcrição local.
- Opção 4 remove um provedor da lista; opção 5 desliga a IA.
