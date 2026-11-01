"""Atendente de WhatsApp (UazAPI): recebe pedidos da equipe, consulta o INTEGRA e responde.

Uso (PowerShell, na pasta do projeto; deixe a janela aberta durante o expediente):
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\atendente_whatsapp.py

1. Abre o Chrome do robo -> faca o login no INTEGRA (uma vez).
2. Conecta na UazAPI por SSE (conexao de saida; nao precisa abrir porta nem tunel) e,
   como reserva, busca as ultimas mensagens a cada 10 s (cobre quedas do SSE).
3. Cada pedido de numero interno cadastrado e respondido. Ctrl + C encerra.
"""
from __future__ import annotations

from datetime import datetime
import os
import queue
import threading
import time
import urllib.error
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from core.audit import get_logger  # noqa: E402
from core.config import settings  # noqa: E402
from core.store import Store  # noqa: E402

log = get_logger("atendente")


IMAGENS_ACEITAS = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGEM = 3_700_000      # ~5 MB depois do base64 (limite da API)


def provedores_configurados() -> list[str]:
    """IA_PROVEDORES=claude,groq,ollama (ordem fixa de prioridade). Sem a variavel: os que tiverem chave."""
    lista = [x.strip().lower() for x in os.environ.get("IA_PROVEDORES", "").split(",") if x.strip()]
    if not lista:
        if os.environ.get("ANTHROPIC_API_KEY", "").strip():
            lista.append("claude")
        if os.environ.get("GROQ_API_KEY", "").strip():
            lista.append("groq")
        if os.environ.get("OLLAMA_MODELO", "").strip() or os.environ.get("IA_PROVEDOR", "").strip() == "ollama":
            lista.append("ollama")
    return [x for x in ("gemini", "claude", "groq", "ollama") if x in lista]


def montar_orquestrador(ia_claude):
    """Claude -> Groq -> Ollama com troca automatica. Devolve None se a IA estiver desligada."""
    if os.environ.get("WA_IA_ENABLED", "").strip().lower() != "true":
        print("IA: desligada (WA_IA_ENABLED=false)")
        return None
    from integrations import ia_openai
    from integrations.ia_orquestrador import Orquestrador, Provedor, pausa_para
    provedores = []
    for nome in provedores_configurados():
        if nome == "claude":
            cfg = ia_claude.config()
            if ia_claude.problemas(cfg):
                continue
            teste = lambda c=cfg: ia_claude.teste_rapido(c)  # noqa: E731
            fn = lambda t, f, i, h, c=cfg, **kw: ia_claude.responder(t, f, imagem=i, historico=h, c=c, **kw)  # noqa: E731
            prov = Provedor("claude", fn, le_imagem=True, le_pdf=True)
        else:
            cfg = ia_openai.config(nome)
            if ia_openai.problemas(cfg):
                continue
            teste = lambda c=cfg: ia_openai.teste_rapido(c)  # noqa: E731
            fn = lambda t, f, i, h, c=cfg, **kw: ia_openai.responder(t, f, imagem=i, historico=h, c=c, **kw)  # noqa: E731
            prov = Provedor(nome, fn, le_imagem=bool(cfg.get("VISAO")), le_pdf=True)
        try:
            modelo = teste()
            print(f"IA: {nome.capitalize()} pronto ({modelo})")
        except Exception as exc:
            prov.ultimo_erro = str(exc)
            prov.pausado_ate = time.time() + pausa_para(str(exc))
            print(f"IA: {nome.capitalize()} indisponivel agora ({exc}) - nova tentativa automatica depois")
        provedores.append(prov)
    if not provedores:
        print("IA: nenhum provedor configurado (rode CONFIGURAR_IA.bat) - atendendo so os pedidos fixos")
        return None
    print("IA: ordem de uso -> " + " > ".join(p.nome.capitalize() for p in provedores)
          + " (troca automatica se um falhar)")
    orq = Orquestrador(provedores)
    orq._salvar()
    return orq


def preparar_ia_e_voz(uazapi):
    """Liga IA (Claude), transcricao local e voz conforme o .env. Tudo opcional:
    sem isso o atendente funciona como antes (pedidos fixos em texto)."""
    import base64
    from integrations import ia_claude, voz

    ia = montar_orquestrador(ia_claude)

    transcreve = voz.transcricao_disponivel()
    if transcreve:
        print(f"Audio: transcricao ativa - {voz.descricao_transcricao()}")
        if voz.provedor_transcricao() == "local":
            print("       (na 1a vez o modelo local e baixado; pode demorar alguns minutos)")
            threading.Thread(target=lambda: _pre_carregar(voz), daemon=True).start()
    else:
        print("Audio: desligado (configure a ElevenLabs com scripts\\configurar_elevenlabs.py "
              "ou instale: .\\.venv\\Scripts\\python.exe -m pip install faster-whisper)")

    class Midia:
        def __init__(self):
            self.transcreve = transcreve

        def transcrever(self, msg):
            dados, mime = uazapi.baixar_midia([msg.get("id"), msg.get("id_api")], generate_mp3=True)
            return voz.transcrever(dados, ".mp3" if ("mpeg" in mime or "mp3" in mime) else ".ogg")

        def documento(self, msg):
            dados, mime = uazapi.baixar_midia([msg.get("id"), msg.get("id_api")], generate_mp3=False)
            mime = (mime or "").split(";")[0].strip().lower()
            if mime != "application/pdf" and not dados[:5] == b"%PDF-":
                raise ValueError("FORMATO_DE_DOCUMENTO")
            if len(dados) > MAX_IMAGEM:
                raise ValueError("DOCUMENTO_GRANDE_DEMAIS")
            return base64.b64encode(dados).decode("ascii"), "application/pdf"

        def imagem(self, msg):
            dados, mime = uazapi.baixar_midia([msg.get("id"), msg.get("id_api")], generate_mp3=False)
            mime = (mime or "image/jpeg").split(";")[0].strip().lower()
            if mime not in IMAGENS_ACEITAS:
                raise ValueError("FORMATO_DE_IMAGEM")
            if len(dados) > MAX_IMAGEM:
                raise ValueError("IMAGEM_GRANDE_DEMAIS")
            return base64.b64encode(dados).decode("ascii"), mime

    midia = Midia() if (transcreve or ia) else None

    falar = None
    if transcreve and voz.resposta_em_voz():
        nome = voz.voz_disponivel()
        if nome:
            print(f"Voz: respostas a audios tambem em audio ({nome})")
            falar = lambda numero, texto: uazapi.enviar_audio(numero, *voz.sintetizar(texto))  # noqa: E731
        else:
            print("Voz: indisponivel - respostas so em texto (configure a ElevenLabs ou adicione a voz "
                  "Portugues (Brasil) no Windows: Configuracoes > Hora e idioma > Fala)")
    return ia, midia, falar


def carregar_tratamentos(autorizados: dict) -> dict:
    """{numero: "Dr. Fulano"} a partir do campo opcional 'tratamento' do cadastro de numeros
    (scripts/definir_tratamento.py). Sem tratamento, o robo usa o nome do usuario."""
    import json
    caminho = Path(os.environ.get("WA_RECIPIENTS_FILE", "var/whatsapp-recipients.json"))
    try:
        itens = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {i["phone"]: i["tratamento"] for i in itens
            if isinstance(i, dict) and i.get("tratamento") and i.get("phone") in autorizados}


def _pre_carregar(voz):
    try:
        voz._carregar()
        print("Audio: modelo de transcricao pronto.", flush=True)
    except Exception as exc:
        print(f"Audio: falha ao carregar o modelo ({type(exc).__name__}) - audios terao resposta de erro", flush=True)


def main() -> int:
    from integrations import uazapi
    from integrations.atendente import Atendente
    from integrations.integra import IntegraClient
    from integrations.integra_parser import parse_listagem
    from integrations.whatsapp_integra import cfg, destinatarios

    if os.environ.get("WA_ATENDENTE_ENABLED", "").strip().lower() != "true":
        print("ATENDENTE DESLIGADO: defina WA_ATENDENTE_ENABLED=true no .env")
        return 2
    erros = uazapi.problemas()
    if erros:
        print("CONFIGURACAO UAZAPI INCOMPLETA: " + "; ".join(erros))
        return 2
    try:
        estado = uazapi.status()
    except Exception as exc:
        print(f"UAZAPI INACESSIVEL ({type(exc).__name__}) - confira UAZAPI_URL/UAZAPI_TOKEN")
        return 3
    print(f"UazAPI: instancia {estado}")
    if estado != "connected":
        print("O numero nao esta conectado. Conecte em https://uazapi.dev (QR Code) e rode de novo.")
        return 3

    store = Store(settings.AGENT_DB)
    autorizados = {fone: nome for nome, fone in destinatarios(store, cfg()).items()}
    if not autorizados:
        print("Nenhum numero interno cadastrado (scripts\\manage_whatsapp.py add ...).")
        return 2
    print(f"Numeros autorizados: {', '.join('***' + n[-4:] for n in autorizados)}")

    with IntegraClient() as integra:
        integra.login()
        print("INTEGRA: login confirmado. Atendente pronto - Ctrl + C para encerrar.\n")

        def ler():
            integra.abrir_publicacoes()
            return parse_listagem(integra.html_listagem_publicacoes())

        def navegador_vivo() -> bool:
            try:
                integra.driver.window_handles
                return True
            except Exception:
                return False

        def consultar_hoje():
            try:
                return ler()
            except Exception:   # inclui SESSAO_EXPIRADA (detectada so na listagem) e Chrome fechado
                if not navegador_vivo():
                    print(f"[{datetime.now():%H:%M:%S}] Chrome do robo foi fechado - reabrindo...", flush=True)
                    try:
                        integra.driver.quit()
                    except Exception:
                        pass
                    integra.driver = integra._novo_chrome()
                original = settings.INTEGRA_LOGIN_TIMEOUT
                settings.INTEGRA_LOGIN_TIMEOUT = 15   # tenta reaproveitar a sessao salva no perfil
                try:
                    integra.login()
                except Exception:
                    print(f"[{datetime.now():%H:%M:%S}] ATENCAO: faca o login no INTEGRA na janela do Chrome "
                          "do robo (nao feche essa janela).", flush=True)
                    raise
                finally:
                    settings.INTEGRA_LOGIN_TIMEOUT = original
                return ler()

        ia, midia, falar = preparar_ia_e_voz(uazapi)
        atendente = Atendente(store, autorizados, consultar_hoje, uazapi.enviar_texto,
                              ia=ia, midia=midia, falar=falar, nomes=carregar_tratamentos(autorizados))
        fila: queue.Queue = queue.Queue()
        parar = threading.Event()

        def ouvir_sse():   # thread so recebe; o INTEGRA (Selenium) e usado so pela thread principal
            for ev in uazapi.eventos(parar=parar.is_set):
                fila.put(("sse", ev))

        threading.Thread(target=ouvir_sse, daemon=True).start()
        inicio = time.time() - 5          # nao responde mensagens antigas (antes de ligar)
        proxima_busca, busca_ok = 0.0, True
        from integrations.painel_robo import batimento
        proximo_sinal = 0.0

        def tratar(msg, origem):
            if not msg or msg.get("de_mim") or msg.get("pela_api") or not msg.get("id"):
                return   # eco das respostas do robo e eventos sem mensagem (confirmacoes de leitura etc.)
            if atendente.ja_visto(msg.get("id")):
                return   # ja tratada (chegou pelo SSE e pela busca): silencioso
            try:
                resposta = atendente.processar(msg)
            except Exception as exc:   # banco ocupado etc.: nao derruba o atendente
                print(f"[{datetime.now():%H:%M:%S}] erro ao processar pedido ({type(exc).__name__})")
                return
            numero = atendente._autorizado(msg.get("numero") or "")
            hora = f"[{datetime.now():%H:%M:%S}]"
            if numero not in autorizados:
                quem = f"***{numero[-4:]}" if numero else "numero oculto pelo WhatsApp"
                print(f"{hora} mensagem de numero NAO cadastrado ({quem}) - ignorada", flush=True)
                return
            if resposta:
                tipo = msg.get("tipo") or "texto"
                extra = ""
                try:
                    res = atendente.resultado(msg.get("id"))
                except Exception:
                    res = ""
                if "+voz" in res:
                    extra = " + audio enviado"
                elif "voz_falhou" in res:
                    extra = " | AUDIO FALHOU: " + res.split("voz_falhou:", 1)[1][:80]
                elif tipo == "audio" and atendente.falar is None:
                    extra = " | sem audio: voz desligada (veja a linha 'Voz:' ao iniciar)"
                elif tipo == "audio":
                    extra = " | sem audio nesta resposta"
                if ":ia_falhou:" in res:
                    extra += " | IA falhou: " + res.split(":ia_falhou:", 1)[1].split(";")[0][:60]
                print(f"{hora} pedido de {autorizados[numero]} ({origem}, {tipo}): respondido{extra}", flush=True)
            elif not (msg.get("texto") or "").strip() and (msg.get("tipo") or "texto") == "texto" \
                    or msg.get("tipo") == "ignorar":
                return   # reacao, edicao ou mensagem vazia: silencioso
            else:
                print(f"{hora} pedido de {autorizados[numero]} ({origem}): sem resposta "
                      "(robo pausado ou falha no envio)", flush=True)

        try:
            while True:
                try:
                    origem, ev = fila.get(timeout=2)
                    tratar(uazapi.extrair_mensagem(ev), origem)
                except queue.Empty:
                    pass
                if time.time() >= proximo_sinal:              # sinal de vida para o painel
                    proximo_sinal = time.time() + 10
                    batimento()
                if busca_ok and time.time() >= proxima_busca:   # reserva: a cada 10 s
                    proxima_busca = time.time() + 10
                    for fone in autorizados:
                        try:
                            msgs = uazapi.buscar_mensagens(fone)
                        except urllib.error.HTTPError as exc:
                            if exc.code in (404, 405):
                                busca_ok = False
                                print("Aviso: busca de reserva indisponivel neste servidor; usando so o SSE.")
                                break
                            continue
                        except Exception:
                            continue
                        for m in sorted(msgs, key=lambda x: x.get("ts", 0)):
                            if m.get("ts", 0) >= inicio:
                                tratar(m, "busca")
        except KeyboardInterrupt:
            parar.set()
            print("\nAtendente encerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

