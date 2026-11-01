# Log de validação cruzada — Etapa INTEGRA (08/10/2026)

Protocolo: nenhuma etapa avança sem validação dos 2 agentes. Em caso de divergência, o Agente 1 decide sobre configuração e o Agente 2 decide sobre integração e comunicação.

| Agente | Ação | Resultado |
|---|---|---|
| [1.1 Config] | Revisão de `core/config.py` e `.env.example` | Sem credenciais embutidas; defaults seguros (login manual, perfil exclusivo) |
| [1.1 Config] | Teste com variável vazia (`INTEGRA_LOGIN_TIMEOUT=`) | **Falha** de import → corrigido com `_int()` |
| [1.2 Código] | APIs do Selenium 4.25, caminhos no Windows, encoding UTF-8 | OK |
| [1.3 Inconsist.] | Busca por escritas no INTEGRA e por `clickVisualizar` | Nenhuma: tarefas, retorno, conclusão e visualização bloqueados |
| [1.3 Inconsist.] | Pausa dupla (`.paused` + painel) | Ambas respeitadas (com teste) |
| [1.3 Inconsist.] | Rodapé antigo "Exibindo 0 de 0" lido como resultado | **Alta** → corrigido: a listagem local é limpa antes de pesquisar |
| [1.3 Inconsist.] | Erros do navegador sem tratamento | **Média** → corrigido: viram `ERRO_NAVEGADOR`, saída 3 e registro na auditoria |
| [2.1 Íntegra] | Simulação de 6 cenários com driver falso | Normal, modal, sem rodapé, 0 de 0, sessão expirada e sem resposta: todos com o resultado correto |
| [2.1 Íntegra] | Botão "Pesquisar" ambíguo e modal interceptando o clique | Corrigido: busca o botão no formulário e tenta de novo após fechar o aviso |
| [2.1 Íntegra] | Espera pelo rodapé "Exibindo N de M" | Corrigido: sem rodapé, o resultado é PARCIAL e não vira zero |
| [2.2 WhatsApp] | Busca por envios nesta etapa | Nenhum envio; a ponte não é importada em lugar nenhum |
| [2.2 WhatsApp] | Nome do evento futuro | Ajustado para `aviso_integra_publicacoes`, separado da auditoria |
| [2.3 Cruzado] | Comandos, flags, chaves e resultados do documento comparados com o código | Batem; códigos de erro que faltavam foram acrescentados |
| [Coordenação] | Caminho do usuário Windows na auditoria; `.env` no modo offline; travessão no print | Corrigidos |
| [Coordenação] | 15 testes offline + teste offline T1–T4 + simulação do fluxo | **OK** |

**Veredito:** Agente 1 APROVADO (configuração) · Agente 2 APROVADO (integração e estrutura de WhatsApp inativa). Consenso: **liberado para o teste ao vivo no computador do usuário.**

Ressalvas que só o teste ao vivo resolve: Selenium real, formato da tela com 0 resultados, paginação, `clickVisualizar` e conferência por diff com o `config.py` original.

## Teste ao vivo no computador do usuário (08/10/2026, 22:52)

| Etapa | Resultado |
|---|---|
| Rodada 1 | T5 OK; `BOTAO_PESQUISAR_NAO_ENCONTRADO` → busca do botão reforçada e diagnóstico automático adicionado |
| Rodada 2 | O menu abria o módulo 132 ("Publicações jurídicas") → `INTEGRA_PUBLICACOES_URL` = módulo 38 |
| Rodada 3 | `LISTAGEM_NAO_CARREGOU` (a área da lista era esvaziada antes da pesquisa) → o robô passou a ler a resposta de `publicacoesListar.asp` |
| Rodada 4 | **T1–T7 OK: 6 publicações, rodapé "Exibindo 6 de 6", 2 com vínculo pendente → `INTEGRACAO_VERIFICADA`** |

## Etapa WhatsApp: validação cruzada (08/10/2026)

| Agente | Ação | Resultado |
|---|---|---|
| [1.1] | Variáveis `WA_*`, padrões e segredos | Desligado por padrão; sem segredos; doc e `.env.example` iguais |
| [1.2] | Fila, transações e idempotência | Envio único por lote e por destinatário |
| [1.3] | Tamanho da mensagem montada > 1024 com muitas publicações | **Alta** → corrigido: limite dinâmico, pior caso ~958 caracteres |
| [1.3] | Teste `--enviar` ignorava o arquivo `.paused` | Corrigido |
| [2.1] | Leitura → gravação → aviso | Aviso só em leitura real; falha no aviso não derruba a leitura |
| [2.2] | Cloud API (template, `wamid`, 4xx/5xx/timeout) | De acordo com a API oficial; sem reenvio cego |
| [2.2] | Template proposto (Utilidade) | Boa chance de aprovação |
| [2.3] | Doc × código | Confere; `manage_whatsapp.py --phone --internal-consent` confere com o script original |
| [Coordenação] | 25 testes offline | **OK** |

**Veredito:** Agente 1 APROVADO · Agente 2 APROVADO. **Liberado para configurar a Meta e testar com 1 número.**

## Etapa WhatsApp v2: UazAPI + atendimento (08/10/2026)

| Agente | Ação | Resultado |
|---|---|---|
| [1.1] | Segredos e padrões | Token só da instância, nunca impresso; tudo desligado por padrão |
| [1.3] | Erro de banco virava "Total: 0" | Corrigido: responde que não conseguiu ler |
| [1.3] | "bom dia, publicações hoje" mostrava só o menu | Corrigido |
| [1.3] | Celular sem o 9 ou JID com sufixo de aparelho não era reconhecido | Corrigido |
| [1.3] | Queda do SSE (IncompleteRead) ou token inválido | Reconexão segura; mostra o tipo do erro sem o token |
| [2.1] | Sessão expirada sem novo login | Corrigido: refaz abrir + listar após o login |
| [2.1] | Atendente "consumia" publicações novas sem avisar | Corrigido: aciona o aviso automático |
| [2.2] | 12 eventos SSE simulados | Respostas, recusas e ignorados corretos; 1 consulta ao INTEGRA (cache) |
| [2.2] | Resposta acima de 3500 caracteres | Corrigido |
| [2.3] | Doc × código | Confere |
| [Coordenação] | 38 testes offline | **OK** |

**Veredito:** Agente 1 APROVADO · Agente 2 APROVADO. Risco aceito pelo escritório: a UazAPI não é a API oficial; usar número exclusivo do robô.

## Etapa IA (Claude) + áudio + imagem (09/10/2026)

| Agente | Ação | Resultado |
|---|---|---|
| [1.1] | Chave da Anthropic, padrões, `.env.example` | IA desligada por padrão; chave só no `.env`, nunca impressa; `configurar_ia.py` preserva escolhas |
| [1.2] | API Messages (ferramentas, imagem, histórico) | Formato conferido; só 4 ferramentas de CONSULTA, nenhuma de escrita |
| [1.3] | Proibidos via áudio, legenda de imagem e texto livre | Recusados **antes** da IA (com teste) |
| [2.1] | Revisão independente: pausa ligada durante pedido longo | **Média** → corrigido: revalida a pausa antes de ler o INTEGRA e antes de enviar |
| [2.1] | Primeiro download do Whisper travava o robô | **Média** → corrigido: responde "preparando transcrição" sem travar |
| [2.2] | Reações (👍), edições e mensagens apagadas viravam chamada paga à IA | Corrigido: ignoradas |
| [2.2] | Limite de imagem, lista grande cortada, `max_tokens`, nome com "x", codificação do PowerShell | Corrigidos |
| [2.3] | Doc × código | Confere |
| [Coordenação] | 63 testes offline | **OK** |

**Veredito:** Agente 1 APROVADO · Agente 2 APROVADO. Ressalvas que só o teste real resolve: instalação do `faster-whisper` no Python 3.14, conversão OGG pelo PyAV (com reserva em WAV) e campos de mídia da UazAPI.

## Etapa ElevenLabs (09/10/2026)

| Agente | Ação | Resultado |
|---|---|---|
| [1.1] | Chave (`xi-api-key`) só no `.env`; erros mostram só o código e o status | OK (com teste) |
| [2.2] | TTS `POST /v1/text-to-speech/{voz}` (MP3) e STT `POST /v1/speech-to-text` (`scribe_v2`, `por`) conferidos com a documentação oficial | OK |
| [2.1] | MP3 convertido em nota de voz OGG/Opus quando o PyAV existe; senão envia MP3 | Reserva testada |
| [2.3] | Provedores: escolha explícita no `.env` ou automática pela chave; a opção local continua funcionando | OK |
| [Coordenação] | 70 testes offline | **OK** |
