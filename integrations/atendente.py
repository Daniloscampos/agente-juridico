"""Atendente de WhatsApp: o advogado pede, o robo consulta o INTEGRA e responde.

Regras (iguais as permissoes do robo):
  * so atende numeros da equipe interna cadastrados (scripts/manage_whatsapp.py), nunca grupos;
  * somente CONSULTA. Pedidos de protocolar, assinar, pagar, marcar como lida, enviar a cliente
    ou apagar sao recusados com explicacao;
  * robo pausado (arquivo .paused ou painel) = nao consulta e nao responde (so registra);
  * se o INTEGRA falhar, responde que NAO conseguiu consultar (nunca "nada encontrado");
  * cada pedido e respondido uma unica vez (id da mensagem) e fica na auditoria (sem conteudo).

Pedidos aceitos (v1):
  ajuda | publicacoes hoje | publicacoes DD/MM/AAAA | processo NNNNNNN-DD.AAAA.J.TR.OOOO | sem vinculo
"""
from __future__ import annotations

from datetime import datetime
import json
import os
import re
import time
import unicodedata

from core import control
from core.policy import Blocked, enforce
from core.store import now

CNJ_RE = re.compile(r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})")
DATA_RE = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
PROIBIDOS = ("protocol", "assin", "pagar", "pagamento", "boleto", "marcar como lida", "marque como lida",
             "visualizar", "enviar ao cliente", "enviar para o cliente", "mandar para o cliente",
             "excluir", "apagar", "deletar", "senha", "certificado")
MAX_TEXTO = 3500
LIMITE_POR_MINUTO = 8
CACHE_SEGUNDOS = 180
HIST_SEGUNDOS = 1800        # memoria curta da conversa (30 min) para a IA
HIST_PARES = 4
MAX_PUBS_IA = 50            # itens enviados a IA por consulta (o total vai sempre)

EXEMPLOS = ("• \"Quais são as publicações de hoje?\"\n"
            "• \"Há publicações do processo 0000000-00.0000.0.00.0000?\"\n"
            "• \"Publicações do dia 08/10/2026\"\n"
            "• \"Quais publicações estão sem processo vinculado?\"")
LIMITES = ("Só lembrando: meu papel é consultar e organizar informações; não protocolo, não assino "
           "e não mexo no processo.")
AJUDA = ("Sou o assistente virtual do escritório. Posso consultar as publicações do INTEGRA pra você: "
         "as de hoje, as de uma data específica ou as de um processo. Pode pedir por texto ou por áudio. "
         "Em que posso ajudar?")

# Respostas variadas: a mesma pessoa nunca recebe o mesmo texto de apoio duas vezes seguidas.
VARIANTES = {
    "nao_entendi": (
        "Não consegui entender bem o que você precisa. Quer que eu veja as publicações de hoje, "
        "de uma data específica ou de algum processo?",
        "Desculpa, ainda não peguei o pedido. Se me passar o número do processo, eu verifico as "
        "publicações dele. Também posso ver as de hoje, se preferir.",
        "Acho que não captei direito. Pode me contar de outro jeito? Por exemplo: \"publicações de ontem\" "
        "ou o número do processo.",
    ),
    "analise_instavel": (
        "Poxa, eu gostaria de te responder isso por completo agora, mas estou com uma instabilidade na "
        "análise mais aprofundada. Enquanto isso, já consigo adiantar as consultas do INTEGRA: quer que eu "
        "veja as publicações de hoje ou de algum processo?",
        "Ainda estou com essa instabilidade na análise, mas não quero te deixar na mão. Me passa o número "
        "do processo que eu verifico as publicações dele?",
        "Essa parte da análise segue instável por aqui. Se ajudar, posso ver as publicações de uma data "
        "específica; é só me dizer o dia.",
    ),
    "arquivo_instavel": (
        "Poxa, não consegui analisar esse arquivo agora; a leitura de documentos está instável. Se me passar "
        "o número do processo, já verifico as publicações dele.",
        "A leitura do arquivo ainda não deu certo, desculpa. Enquanto isso, posso consultar as publicações "
        "do processo, se você me disser o número.",
    ),
    "excesso": (
        "Opa, chegaram vários pedidos seguidos. Me dá um minutinho e manda de novo, por favor?",
        "Ainda estou dando conta dos pedidos anteriores. Em um minutinho eu sigo com você, tudo bem?",
    ),
}
SAUDACAO_INTERVALO = 1800   # cumprimenta de novo apos 30 min sem conversa


def saudacao(nome: str, agora: datetime | None = None) -> str:
    h = (agora or datetime.now()).hour
    periodo = "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"
    return f"{periodo}, {nome}." if nome else f"{periodo}."


def motivo_amigavel(exc: Exception) -> str:
    """Explica a falha em linguagem simples (sem nomes tecnicos)."""
    t = f"{type(exc).__name__} {exc}".lower()
    if "pausad" in t:
        return "o robô está pausado no momento"
    if any(k in t for k in ("invalidsessionid", "nosuchwindow", "webdriver", "chrome_nao_iniciou", "navegador")):
        return "a janela do sistema no computador do escritório foi fechada; já estou providenciando a reabertura"
    if any(k in t for k in ("sessao", "login", "expirad")):
        return "o acesso ao sistema expirou e precisa ser renovado no computador do escritório"
    if "timeout" in t:
        return "o sistema demorou mais do que o normal para responder"
    return "houve uma falha de comunicação com o sistema"


SCHEMA = """
CREATE TABLE IF NOT EXISTS whatsapp_inbox(
    msg_id TEXT PRIMARY KEY, numero TEXT NOT NULL, recebido TEXT NOT NULL,
    comando TEXT NOT NULL, resultado TEXT NOT NULL);
"""


def _normal(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t).strip()


DIAS = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")
AGENDA_RE = re.compile(r"\b(agenda|prazos?|audiencias?|compromissos?|vencimentos?|pauta)\b")


def data_relativa(t: str, hoje=None, futuro: bool = False):
    """'ontem', 'amanha', 'terca da semana que vem', 'sexta passada' -> date (ou None). t ja normalizado."""
    from datetime import date, timedelta
    hoje = hoje or date.today()
    if "anteontem" in t:
        return hoje - timedelta(days=2)
    if re.search(r"\bontem\b", t):
        return hoje - timedelta(days=1)
    if "depois de amanha" in t:
        return hoje + timedelta(days=2)
    if re.search(r"\bamanha\b", t):
        return hoje + timedelta(days=1)
    citados = sorted(((m.start(), i) for i, nome in enumerate(DIAS)
                      for m in re.finditer(rf"\b{nome}(-feira| feira)?\b", t)), reverse=True)
    for _, i in citados[:1]:   # "segunda e feriado, quero terca da semana que vem" -> terca
        if re.search(r"(que vem|proxima|seguinte)", t):
            delta = (i - hoje.weekday()) % 7 or 7
            if "semana que vem" in t or "proxima semana" in t:   # dia da PROXIMA semana
                segunda_prox = hoje + timedelta(days=7 - hoje.weekday())
                return segunda_prox + timedelta(days=i)
            return hoje + timedelta(days=delta)
        if re.search(r"(passad|ultim)", t) or not futuro:
            return hoje - timedelta(days=((hoje.weekday() - i) % 7 or 7))
        return hoje + timedelta(days=((i - hoje.weekday()) % 7 or 7))
    return None


def interpretar(texto: str) -> tuple[str, str]:
    """Devolve (comando, argumento).
    comando: ajuda|hoje|data|processo|sem_vinculo|agenda|proibido|desconhecido"""
    t = _normal(texto)
    if not t:
        return "desconhecido", ""
    if any(p in t for p in PROIBIDOS):
        return "proibido", ""
    m = CNJ_RE.search(texto or "")
    if m:
        return "processo", "".join(m.groups())
    if "sem vinculo" in t or "sem processo" in t or "nao vinculad" in t:
        return "sem_vinculo", ""
    d = DATA_RE.search(t)
    if "public" not in t and (AGENDA_RE.search(t) or (re.search(r"\bprocessos?\b", t)
                                                      and (d or data_relativa(t, futuro=True)))):
        quando = d.group(0) if d else data_relativa(t, futuro=True)
        return "agenda", (quando if isinstance(quando, str) else quando.strftime("%d/%m/%Y") if quando else "")
    if d and "public" in t or (d and t.strip() == d.group(0)):
        return "data", d.group(0)
    rel = data_relativa(t) if "public" in t and "hoje" not in t else None
    if rel:
        return "data", rel.strftime("%d/%m/%Y")
    if "public" in t and ("hoje" in t or t in {"publicacoes", "publicacao"}) or t == "hoje":
        return "hoje", ""
    # Saudacao/ajuda por ultimo: "bom dia, publicacoes hoje" deve consultar, nao so mostrar o menu.
    if re.search(r"\b(ajuda|menu|comandos|oi|ola|bom dia|boa tarde|boa noite)\b", t):
        return "ajuda", ""
    return "desconhecido", ""


def _linha(i: int, p: dict) -> str:
    procs = p.get("processos") or []
    oc = p.get("orgao_comarca") or ""
    comarca = oc.rsplit(" - ", 1)[-1] if " - " in oc else ""
    vara = " - ".join(x for x in (p.get("orgao") or oc or "órgão não informado", comarca) if x)
    titulo = ("Processo " + ", ".join(x["numero_cnj"] for x in procs)) if procs \
        else "Publicação ainda sem processo vinculado"
    return f"{i}) {titulo}\n    {vara}\n    Disponibilizada em {p.get('data_disponibilizacao') or 'data não informada'}"


def contagem(pubs: list[dict]) -> str:
    n = len(pubs)
    pend = sum(1 for p in pubs if not p.get("processos"))
    if n == 0:
        return "nenhuma publicação"
    base = "1 publicação" if n == 1 else f"{n} publicações"
    if pend:
        base += (", ainda sem processo vinculado" if pend == n == 1 else
                 f", sendo {pend} ainda sem processo vinculado" if pend < n else ", todas ainda sem processo vinculado")
    return base


def texto_para_voz(resposta: str) -> str:
    """Nota de voz curta e natural: so a abertura (os detalhes ficam no texto). Economiza creditos de voz."""
    corpo = resposta.split("\n\n", 1)[1] if resposta.startswith("🎙️") and "\n\n" in resposta else resposta
    partes = [p for p in corpo.split("\n\n") if p.strip()]
    if not partes:
        return corpo
    abertura = partes[0].rstrip(":").strip()
    if len(partes) > 1 and re.match(r"^\d+\)", partes[1].strip()):
        return abertura + ". Os detalhes de cada publicação estão na mensagem de texto."
    return corpo


def formatar(intro: str, pubs: list[dict], rodape: str = "") -> str:
    """intro: frase completa de abertura; rodape: observacoes/fecho."""
    if not pubs:
        return intro + ("\n\n" + rodape if rodape else "")
    partes, usados = [intro, ""], 0
    reserva = len(rodape) + 120
    for i, p in enumerate(pubs, 1):
        linha = _linha(i, p)
        if len("\n\n".join(partes)) + len(linha) + reserva > MAX_TEXTO:
            break
        partes.append(linha)
        usados += 1
    texto = partes[0] + "\n\n" + "\n\n".join(partes[2:])
    if usados < len(pubs):
        resto = len(pubs) - usados
        texto += f"\n\n…e mais {resto} {'publicação' if resto == 1 else 'publicações'}, disponíveis no painel do robô."
    if rodape:
        texto += "\n\n" + rodape
    return texto


class Atendente:
    def __init__(self, store, autorizados: dict, consultar_hoje, enviar, ia=None, midia=None, falar=None,
                 nomes: dict | None = None):
        """autorizados: {numero: usuario}; consultar_hoje() -> ResultadoListagem (ao vivo);
        enviar(numero, texto) -> id.
        Opcionais (IA/voz, ligados pelo .env):
          ia(texto, ferramentas, imagem, historico) -> texto        (integrations.ia_claude.responder)
          midia.transcrever(msg) -> texto ; midia.imagem(msg) -> (base64, media_type)
          falar(numero, texto) -> envia nota de voz
          nomes: {numero: "Dr. Fulano"} forma de tratamento (padrao: nome do usuario)"""
        self.store = store
        self.autorizados = autorizados
        self.consultar_hoje = consultar_hoje
        self.enviar = enviar
        self.ia = ia
        self.midia = midia
        self.falar = falar
        self._hist: dict[str, list] = {}
        self.nomes = nomes or {}
        self._contato: dict[str, float] = {}
        self._ultima_var: dict[tuple, int] = {}
        self._cache = (0.0, None)
        self._janela: dict[str, list[float]] = {}
        with store.db() as db:
            db.executescript(SCHEMA)

    # -- utilitarios -------------------------------------------------------
    def _registrar(self, msg_id, numero, comando, resultado) -> bool:
        """True se o pedido e novo (evita responder duas vezes)."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            cur = db.execute("INSERT OR IGNORE INTO whatsapp_inbox VALUES(?,?,?,?,?)",
                             (msg_id, numero, now(), comando, resultado))
            novo = cur.rowcount == 1
            if novo:
                self.store._audit(db, {"action": "atendimento_whatsapp", "actor": "robo",
                                       "recipient_key": self.autorizados.get(numero, "nao_autorizado"),
                                       "comando": comando, "result": resultado})
            return novo

    def ja_visto(self, msg_id) -> bool:
        """True se esta mensagem ja foi registrada (respondida, ignorada ou em andamento)."""
        if not msg_id:
            return False
        with self.store.db() as db:
            return db.execute("SELECT 1 FROM whatsapp_inbox WHERE msg_id=?", (msg_id,)).fetchone() is not None

    def _autorizado(self, numero: str) -> str:
        """Casa o JID com o cadastro. Celular BR antigo pode vir sem o 9 (55 DD 8 digitos)."""
        if numero in self.autorizados:
            return numero
        if re.fullmatch(r"55\d{2}[6-9]\d{7}", numero):
            com9 = numero[:4] + "9" + numero[4:]
            if com9 in self.autorizados:
                return com9
        if re.fullmatch(r"55\d{2}9[6-9]\d{7}", numero):
            sem9 = numero[:4] + numero[5:]
            if sem9 in self.autorizados:
                return sem9
        return numero

    def resultado(self, msg_id) -> str:
        """Resultado registrado da mensagem (ex.: 'respondido:...+voz' ou '...;voz_falhou:...')."""
        with self.store.db() as db:
            r = db.execute("SELECT resultado FROM whatsapp_inbox WHERE msg_id=?", (msg_id,)).fetchone()
        return r[0] if r else ""

    def _atualizar(self, msg_id, resultado):
        with self.store.db() as db:
            db.execute("UPDATE whatsapp_inbox SET resultado=? WHERE msg_id=?", (resultado, msg_id))

    def _nome(self, numero) -> str:
        if self.nomes.get(numero):
            return self.nomes[numero]
        u = str(self.autorizados.get(numero) or "")
        return u[:1].upper() + u[1:] if u and u not in ("admin", "robo") else ""

    def _saud(self, numero) -> str:
        """Cumprimento so no inicio da conversa (ou apos 30 min sem falar)."""
        if not numero:
            return ""
        agora = time.time()
        ultimo = self._contato.get(numero, 0)
        self._contato[numero] = agora
        return saudacao(self._nome(numero)) + " " if agora - ultimo > SAUDACAO_INTERVALO else ""

    def _variar(self, numero, chave) -> str:
        opcoes = VARIANTES[chave]
        ultimo = self._ultima_var.get((numero, chave), -1)
        k = (ultimo + 1) % len(opcoes)
        self._ultima_var[(numero, chave)] = k
        return opcoes[k]

    def _excesso(self, numero) -> bool:
        agora = time.time()
        lista = [t for t in self._janela.get(numero, []) if agora - t < 60]
        lista.append(agora)
        self._janela[numero] = lista
        return len(lista) > LIMITE_POR_MINUTO

    def _base(self) -> list[dict]:
        """Erro de leitura da base levanta excecao (nunca vira lista vazia = 'zero')."""
        with self.store.db() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='integra_publicacoes'").fetchone():
                return []                      # base ainda nao criada: realmente nada lido
            rows = db.execute("SELECT payload FROM integra_publicacoes ORDER BY primeira_leitura DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def _desde(self) -> str:
        with self.store.db() as db:
            try:
                r = db.execute("SELECT MIN(primeira_leitura) FROM integra_publicacoes").fetchone()[0]
            except Exception:
                r = None
        try:   # gravado em UTC (store.now); mostra a data local no formato DD/MM/AAAA
            return datetime.fromisoformat(r).astimezone().strftime("%d/%m/%Y")
        except (TypeError, ValueError):
            return (r or "")[:10]

    def _hoje_ao_vivo(self):
        ts, res = self._cache
        if res is not None and time.time() - ts < CACHE_SEGUNDOS:
            return res
        if control.is_paused():                # pausa pode ter sido ligada durante o pedido
            raise Blocked("PAUSADO")
        enforce(self.store, "agenda")          # leitura do INTEGRA (mesma regra do ciclo)
        res = self.consultar_hoje()            # levanta excecao se nao conseguir consultar
        from integrations.integra_publicacoes import gravar
        novos: list = []
        resumo = gravar(self.store, res, origem="whatsapp", novos_out=novos)
        if novos:   # sem isto o aviso automatico do ciclo nunca sairia para estas publicacoes
            try:
                from integrations.whatsapp_integra import avisar
                avisar(self.store, novos, resumo)
            except Exception:
                pass    # aviso nunca derruba o atendimento (fica pendente na fila)
        self._cache = (time.time(), res)
        return res

    # -- principal -----------------------------------------------------------
    def processar(self, msg: dict) -> str | None:
        """Recebe a mensagem normalizada (uazapi.extrair_mensagem). Devolve o texto respondido."""
        if not msg or msg.get("de_mim") or msg.get("grupo") or msg.get("pela_api") or not msg.get("id"):
            return None
        numero = self._autorizado(msg.get("numero") or "")
        if numero not in self.autorizados:
            self._registrar(msg["id"], numero or "desconhecido", "ignorado", "nao_autorizado")
            return None                         # fora da equipe interna: nao responde
        tipo = msg.get("tipo") or "texto"
        if tipo == "ignorar" or (tipo == "texto" and not (msg.get("texto") or "").strip()):
            self._registrar(msg["id"], numero, "ignorado", "reacao_ou_vazio")   # reacao, edicao, apagada
            return None
        comando, arg = interpretar(msg.get("texto", ""))
        registro = comando if tipo == "texto" else tipo
        if not self._registrar(msg["id"], numero, registro, "recebido"):
            return None                         # ja respondido
        if control.is_paused():
            self._atualizar(msg["id"], "bloqueado_pausa")
            return None
        try:
            enforce(self.store, "aviso_interno")
        except Blocked as exc:
            self._atualizar(msg["id"], f"bloqueado:{exc}")
            return None
        voz = False
        if self._excesso(numero):
            resposta = self._variar(numero, "excesso")
        else:
            resposta, voz, origem = self._resolver(msg, tipo, comando, arg, numero)
            registro = f"{registro}:{origem}"
        if control.is_paused():                 # pausado enquanto a IA/INTEGRA trabalhava: nao envia
            self._atualizar(msg["id"], "bloqueado_pausa")
            return None
        try:
            self.enviar(numero, resposta)
            self._atualizar(msg["id"], f"respondido:{registro}")
        except Exception as exc:
            self._atualizar(msg["id"], f"erro_envio:{type(exc).__name__}")
            return None                         # nao enviada: nao reportar como respondida
        if voz and self.falar:
            try:
                self.falar(numero, texto_para_voz(resposta))
                self._atualizar(msg["id"], f"respondido:{registro}+voz")
            except Exception as exc:            # voz e extra: o texto ja foi entregue
                motivo = re.sub(r"[^\w .:-]", "", str(exc))[:60]   # ex.: "HTTP 401 quota_exceeded" (sem chaves)
                self._atualizar(msg["id"], f"respondido:{registro};voz_falhou:{type(exc).__name__} {motivo}".strip())
        return resposta

    # -- IA / midia ------------------------------------------------------------
    def _historico(self, numero) -> list:
        agora = time.time()
        pares = [x for x in self._hist.get(numero, []) if agora - x[0] < HIST_SEGUNDOS][-HIST_PARES:]
        self._hist[numero] = pares
        msgs = []
        for _, pergunta, resposta in pares:
            msgs += [{"role": "user", "content": pergunta}, {"role": "assistant", "content": resposta}]
        return msgs

    def _lembrar(self, numero, pergunta, resposta):
        if pergunta and resposta:
            self._hist.setdefault(numero, []).append((time.time(), pergunta[:1500], resposta[:1500]))

    def _resolver(self, msg, tipo, comando, arg, numero) -> tuple[str, bool, str]:
        """Devolve (resposta, responder_em_voz, origem)."""
        if tipo == "documento":
            texto = msg.get("texto", "")
            comando, arg = interpretar(texto) if texto.strip() else ("desconhecido", "")
            if comando == "proibido":
                return self._responder("proibido", "", numero), False, "proibido"
            if not (self.ia and self.midia and hasattr(self.midia, "documento")):
                return (self._saud(numero) + "Obrigado pelo documento! Por enquanto ainda não consigo ler arquivos "
                        "por aqui, mas se me passar o número do processo eu verifico as publicações dele.",
                        False, "documento_sem_ia")
            try:
                arquivo = self.midia.documento(msg)
            except Exception as exc:
                if "FORMATO" in str(exc):
                    return (self._saud(numero) + "Consigo ler documentos em PDF. Você consegue me mandar o "
                            "arquivo nesse formato?", False, "documento_formato")
                return (self._saud(numero) + "Não consegui abrir esse documento, desculpa. Pode enviar de novo?",
                        False, "documento_falhou")
            return self._via_ia(numero, texto or "Analise este documento.", arquivo, "", False)
        if tipo == "outro":
            return (self._saud(numero) + "Esse tipo de arquivo eu ainda não consigo abrir; texto, áudio, "
                    "foto e PDF funcionam. Posso te ajudar com alguma consulta?",
                    False, "nao_suportado")
        imagem, texto, voz, prefixo = None, msg.get("texto", ""), False, ""
        if tipo == "audio":
            if not (self.midia and getattr(self.midia, "transcreve", True)):
                return (self._saud(numero) + "Por enquanto não consigo ouvir áudios. "
                        "Pode me mandar o pedido por escrito?", False, "audio_desligado")
            try:
                texto = self.midia.transcrever(msg)
            except Exception as exc:
                if "MODELO_CARREGANDO" in str(exc):
                    return (self._saud(numero) + "Ainda estou me preparando para ouvir áudios. "
                            "Se puder, me manda o pedido por escrito que eu já vejo.",
                            False, "audio_carregando")
                return (self._saud(numero) + "Não consegui entender o áudio, desculpa. Pode "
                        "mandar de novo ou, se preferir, escrever o pedido?", False, "audio_falhou")
            comando, arg = interpretar(texto)
            voz = True
        elif tipo == "imagem":
            comando, arg = interpretar(texto) if texto.strip() else ("desconhecido", "")
            if comando == "proibido":           # legenda proibida: recusa antes de baixar
                return self._responder("proibido", "", numero), False, "proibido"
            if not (self.ia and self.midia):
                return (self._saud(numero) + "Ainda não consigo ler imagens por aqui. Se me "
                        "escrever o número do processo, eu verifico pra você.", False, "imagem_sem_ia")
            try:
                imagem = self.midia.imagem(msg)
            except Exception as exc:
                return (self._saud(numero) + "Não consegui abrir a imagem, desculpa. Pode enviar de novo?",
                        False, "imagem_falhou")

        if comando == "ajuda" and self.ia and len(texto.split()) > 3:
            comando = "desconhecido"            # "me ajuda a achar..." e pedido livre, nao o menu
        if comando == "proibido":               # regra fixa: nunca passa pela IA
            return prefixo + self._responder("proibido", "", numero), voz, "proibido"
        if imagem is None and comando != "desconhecido" and not (comando == "agenda" and self.ia):
            # pedidos conhecidos: resposta direta e exata (sem custo de IA)
            resposta = prefixo + self._responder(comando, arg, numero)
            self._lembrar(numero, texto, resposta)
            return resposta, voz, "direto"
        if not self.ia:
            return prefixo + self._responder(comando, arg, numero), voz, "direto"
        return self._via_ia(numero, texto, imagem, prefixo, voz)

    def _via_ia(self, numero, texto, arquivo, prefixo, voz) -> tuple[str, bool, str]:
        inicio = self._saud(numero)
        try:
            enforce(self.store, "resumo")       # Limites do painel: "Resumo de informações"
        except Blocked:
            return (prefixo + inicio + "Esse tipo de análise está reservado para a equipe por enquanto. Mas "
                    "posso consultar as publicações do INTEGRA: de hoje, de uma data ou de um processo. Qual prefere?",
                    voz, "ia_bloqueada")
        try:
            resposta = self.ia(texto, self._ferramentas(), arquivo, self._historico(numero),
                               pessoa=self._nome(numero), cumprimentar=bool(inicio))
        except Exception as exc:
            motivo = str(exc)
            if "SEM_VISAO" in motivo:
                return (inicio + "Essa imagem eu não consigo ler agora. Se tiver o documento em PDF, pode me "
                        "mandar; ou me passa o número do processo que eu consulto pra você.", False, "ia_sem_visao")
            if "PDF_SEM_TEXTO" in motivo:
                return (inicio + "Esse PDF parece ser escaneado, então não consegui ler o texto. Você tem uma "
                        "versão com texto selecionável? Ou me diz o número do processo que eu consulto.",
                        False, "pdf_sem_texto")
            if "PDF_SEM_LEITOR" in motivo:
                return (inicio + "Ainda não consigo ler PDFs por aqui. Enquanto isso, "
                        "me passa o número do processo que eu verifico as publicações dele?", False, "pdf_sem_leitor")
            causa = re.sub(r"[^\w .:-]", "", motivo)[:60]          # so para o registro (nunca para a pessoa)
            if arquivo is not None:
                return inicio + self._variar(numero, "arquivo_instavel"), False, f"ia_falhou:{causa}"
            return prefixo + inicio + self._variar(numero, "analise_instavel"), voz, f"ia_falhou:{causa}"
        resposta = (prefixo + resposta.strip())[:MAX_TEXTO]
        self._lembrar(numero, texto or "(arquivo)", resposta)
        return resposta, voz, "ia"

    def _pub_ia(self, p: dict) -> dict:
        """Dados de uma publicacao para a IA (partes so com WA_INCLUIR_PARTES=true)."""
        procs = p.get("processos") or []
        d = {"processos": [x.get("numero_cnj") for x in procs] or "SEM PROCESSO VINCULADO",
             "orgao": p.get("orgao"), "orgao_comarca": p.get("orgao_comarca"),
             "disponibilizacao": p.get("data_disponibilizacao"), "inclusao": p.get("data_inclusao")}
        if os.environ.get("WA_INCLUIR_PARTES", "").strip().lower() == "true":
            d["partes"] = [" x ".join(n for n in (x.get("cliente"), x.get("parte_adversa")) if n) for x in procs]
        return d

    def _ferramentas(self) -> dict:
        def atualizar() -> str:
            try:
                self._hoje_ao_vivo()
                return f"publicações lidas pelo robô no INTEGRA desde {self._desde()} (atualizado agora)"
            except Exception:
                return "publicações já lidas pelo robô; NÃO consegui atualizar com o INTEGRA agora"

        def hoje():
            res = self._hoje_ao_vivo()          # erro sobe -> IA avisa que nao consultou
            pubs = [self._pub_ia(p.to_dict()) for p in res.publicacoes]
            return {"fonte": "INTEGRA ao vivo (tela de publicações)", "lista_completa": res.completo,
                    "total": len(pubs), "sem_vinculo": sum(1 for p in pubs if isinstance(p["processos"], str)),
                    "publicacoes": pubs[:MAX_PUBS_IA], "lista_cortada": len(pubs) > MAX_PUBS_IA}

        def filtrar(regra, rotulo):
            fonte = atualizar()
            pubs = [self._pub_ia(p) for p in self._base() if regra(p)]
            return {"fonte": fonte, "filtro": rotulo, "total": len(pubs), "publicacoes": pubs[:MAX_PUBS_IA],
                    "lista_cortada": len(pubs) > MAX_PUBS_IA}

        def por_processo(numero_cnj: str = ""):
            dig = re.sub(r"\D", "", numero_cnj or "")
            if len(dig) != 20:
                return {"erro": "número CNJ inválido (precisa de 20 dígitos)"}
            return filtrar(lambda p: any(re.sub(r"\D", "", x.get("numero_cnj", "")) == dig
                                         for x in p.get("processos") or []), f"processo {numero_cnj}")

        def por_data(data: str = ""):
            if not DATA_RE.fullmatch((data or "").strip()):
                return {"erro": "data inválida (use DD/MM/AAAA)"}
            d = data.strip()
            return filtrar(lambda p: d in (p.get("data_disponibilizacao"), p.get("data_inclusao")), f"data {d}")

        def sem_vinculo():
            return filtrar(lambda p: not p.get("processos"), "sem processo vinculado")

        def consulta_publica(numero_cnj: str = ""):
            from integrations.consulta_publica import consultar
            return consultar(numero_cnj)

        def agenda(data_inicio: str = "", data_fim: str = ""):
            return {"disponivel": False,
                    "mensagem": "A leitura da agenda, dos prazos e das audiências do INTEGRA ainda não foi "
                                "habilitada no robô. Oriente a pessoa a conferir na agenda do sistema e ofereça "
                                "as consultas de publicações e a consulta pública do processo."}

        def protegido(acao, fn):     # cada ferramenta respeita os Limites definidos no painel
            def chamar(*a, **kw):
                try:
                    enforce(self.store, acao)
                except Blocked as exc:
                    return {"bloqueado": True, "motivo": f"Ação '{acao}' {('pausada' if 'PAUSADO' in str(exc) else 'configurada no painel para exigir intervenção humana')}. Informe a pessoa."}
                return fn(*a, **kw)
            return chamar

        return {"publicacoes_hoje": protegido("agenda", hoje),
                "publicacoes_por_processo": protegido("agenda", por_processo),
                "publicacoes_por_data": protegido("agenda", por_data),
                "publicacoes_sem_vinculo": protegido("agenda", sem_vinculo),
                "consulta_publica_processo": protegido("consulta_publica", consulta_publica),
                "agenda_prazos": protegido("agenda", agenda)}

    def _responder(self, comando: str, arg: str, numero: str = "") -> str:
        saud = self._saud(numero)
        fecho = "Fico à disposição para qualquer detalhe."
        if comando == "ajuda":
            return saud + AJUDA
        if comando == "proibido":
            return (saud + "Essa parte eu não consigo fazer: meu papel é só consultar e organizar informações, "
                    "sem protocolar, assinar, pagar, marcar como lida ou falar com clientes. Isso fica com a equipe. "
                    "Mas posso verificar as publicações relacionadas, se quiser. Qual o número do processo?")
        if comando == "agenda":
            quando = f" para {arg}" if arg else ""
            return (saud + f"Você quer ver a agenda, os prazos ou as audiências{quando}, certo? Essa consulta "
                    "eu ainda não consigo fazer no INTEGRA, então o ideal é conferir direto na agenda do sistema. "
                    "Se ajudar, posso ver as publicações de hoje ou de algum processo. Quer?")
        if comando == "desconhecido":
            if not self.ia:
                return saud + self._variar(numero, "nao_entendi")
            return saud + self._variar(numero, "nao_entendi")
        if comando == "hoje":
            try:
                res = self._hoje_ao_vivo()
            except Exception as exc:
                return (saud + f"Poxa, não consegui acessar o INTEGRA agora: "
                        f"{motivo_amigavel(exc)}. Isso não quer dizer que não haja publicações. "
                        "Me chama de novo daqui a pouquinho que eu confiro pra você.")
            pubs = [p.to_dict() for p in res.publicacoes]
            hora = datetime.fromtimestamp(self._cache[0]).strftime("%H:%M")   # hora real (cache 3 min)
            if pubs:
                intro = f"{saud}Consultei o INTEGRA às {hora} e hoje há {contagem(pubs)}:"
            else:
                intro = f"{saud}Consultei o INTEGRA às {hora} e não há publicações disponibilizadas hoje até o momento."
            aviso = ("Observação: o INTEGRA indicou que a lista pode estar incompleta; recomendo conferir no painel.\n\n"
                     if not res.completo else "")
            return formatar(intro, pubs, aviso + fecho)
        # Consultas na base do robo (publicacoes ja lidas do INTEGRA); atualiza 'hoje' antes.
        try:
            self._hoje_ao_vivo()
            fonte = f"Observação: considerei as publicações registradas pelo robô desde {self._desde()}."
        except Exception:
            fonte = ("Observação: não consegui atualizar com o INTEGRA agora; por isso, a resposta pode não "
                     "incluir as publicações de hoje.")
        try:
            base = self._base()
        except Exception:
            return (saud + "Poxa, não consegui abrir os registros agora. Isso não quer dizer que não haja "
                    "publicações. Me chama de novo daqui a pouquinho que eu confiro pra você.")
        if comando == "sem_vinculo":
            pubs = [p for p in base if not p.get("processos")]
            intro = (f"{saud}Verifiquei os registros e há {contagem(pubs)} aguardando vínculo:" if pubs else
                     f"{saud}Verifiquei os registros e não há publicações sem processo vinculado.")
            return formatar(intro, pubs, fonte + "\n\n" + fecho)
        if comando == "data":
            pubs = [p for p in base if arg in (p.get("data_disponibilizacao"), p.get("data_inclusao"))]
            intro = (f"{saud}Para o dia {arg}, encontrei {contagem(pubs)}:" if pubs else
                     f"{saud}Não encontrei publicações registradas para o dia {arg}.")
            return formatar(intro, pubs, fonte + "\n\n" + fecho)
        if comando == "processo":
            pubs = [p for p in base if any(re.sub(r"\D", "", x["numero_cnj"]) == arg for x in p.get("processos") or [])]
            cnj = f"{arg[:7]}-{arg[7:9]}.{arg[9:13]}.{arg[13]}.{arg[14:16]}.{arg[16:]}"
            intro = (f"{saud}Para o processo {cnj}, encontrei {contagem(pubs)}:" if pubs else
                     f"{saud}Não encontrei publicações registradas para o processo {cnj}.")
            return formatar(intro, pubs, fonte + "\n\n" + fecho)
        return saud + AJUDA
