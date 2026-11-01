"""Orquestrador de IA: o assistente nunca para de responder.

Ordem de prioridade (somente os provedores configurados):
  1. Claude  - modo "completo"     (documentos, raciocínio, fotos)
  2. Groq    - modo "rapido"       (respostas diretas)
  3. Ollama  - modo "contingencia" (conversa fluida com contexto curto; roda no PC)

Se um provedor falha (sem crédito, limite de uso, fora do ar, tempo esgotado), ele fica em pausa
por um tempo proporcional ao problema e o próximo assume na hora, na MESMA mensagem. A pessoa nunca
recebe nomes de modelos nem detalhes técnicos; se a conversa troca de provedor no meio, a resposta
começa com uma frase de transição discreta. O estado fica em var/ia_estado.json (para o painel).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import time

ESTADO = Path("var/ia_estado.json")
TRANSICAO = ""   # sem frase de transição: a pessoa não deve perceber a troca interna (diretriz humanizada)
MODO = {"claude": "completo", "groq": "rapido", "ollama": "contingencia"}
ORDEM = ("claude", "groq", "ollama")
CONVERSA_SEG = 1800


class SemProvedor(RuntimeError):
    pass


@dataclass
class Provedor:
    nome: str
    responder: callable            # (texto, ferramentas, imagem, historico, **kw) -> str
    le_imagem: bool = False
    le_pdf: bool = True
    pausado_ate: float = 0.0
    ultimo_erro: str = ""
    sucessos: int = 0
    falhas: int = 0
    extra: dict = field(default_factory=dict)


def pausa_para(erro: str) -> int:
    """Segundos de pausa conforme o tipo de falha."""
    t = erro.lower()
    if any(k in t for k in ("credit", "balance", "billing", "402", "401", "403", "invalid api key")):
        return 3600          # sem crédito / chave recusada: volta a tentar em 1 h
    if "404" in t or "model" in t and "not" in t:
        return 3600
    if "429" in t or "rate" in t or "limit" in t:
        return 120
    return 60                # fora do ar, tempo esgotado, resposta vazia


class Orquestrador:
    def __init__(self, provedores: list[Provedor], relogio=time.time, gravar_estado: bool = True):
        ordem = {n: i for i, n in enumerate(ORDEM)}
        self.provedores = sorted(provedores, key=lambda p: ordem.get(p.nome, 99))
        self.relogio = relogio
        self.gravar_estado = gravar_estado
        self._ultimo_por_pessoa: dict[str, tuple[str, float]] = {}

    # -- estado -------------------------------------------------------------
    def disponiveis(self, arquivo=None) -> list[Provedor]:
        agora = self.relogio()
        tipo = arquivo[1] if arquivo else None
        saida = []
        for p in self.provedores:
            if p.pausado_ate > agora:
                continue
            if tipo and tipo != "application/pdf" and not p.le_imagem:
                continue
            if tipo == "application/pdf" and not p.le_pdf:
                continue
            saida.append(p)
        return saida

    def estado(self) -> dict:
        agora = self.relogio()
        return {"atualizado": datetime.now(timezone.utc).isoformat(),
                "provedores": [{"nome": p.nome, "modo": MODO.get(p.nome, "completo"),
                                "disponivel": p.pausado_ate <= agora,
                                "volta_em_seg": max(0, int(p.pausado_ate - agora)),
                                "ultimo_erro": p.ultimo_erro[:80], "sucessos": p.sucessos, "falhas": p.falhas}
                               for p in self.provedores]}

    def _salvar(self):
        if not self.gravar_estado:
            return
        try:
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            ESTADO.write_text(json.dumps(self.estado(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    # -- chamada principal (mesma assinatura do responder do Claude) ----------
    def __call__(self, texto, ferramentas, imagem=None, historico=None, pessoa: str = "",
                 cumprimentar: bool = False, **_):
        candidatos = self.disponiveis(imagem)
        if not candidatos:
            self._salvar()
            if imagem and imagem[1] != "application/pdf" and not any(p.le_imagem for p in self.provedores):
                raise SemProvedor("SEM_VISAO")
            raise SemProvedor("SEM_PROVEDOR_DISPONIVEL")
        ultimo_erro = None
        for p in candidatos:
            try:
                resposta = p.responder(texto, ferramentas, imagem, historico, pessoa=pessoa,
                                       cumprimentar=cumprimentar, modo=MODO.get(p.nome, "completo"))
            except Exception as exc:
                msg = str(exc)
                if "SEM_VISAO" in msg or "PDF_SEM" in msg:      # limitação do arquivo, não do provedor
                    ultimo_erro = exc
                    continue
                p.falhas += 1
                p.ultimo_erro = f"{type(exc).__name__}: {msg}"
                p.pausado_ate = self.relogio() + pausa_para(msg)
                ultimo_erro = exc
                continue
            p.sucessos += 1
            p.ultimo_erro = ""
            anterior = self._ultimo_por_pessoa.get(pessoa)
            agora = self.relogio()
            self._ultimo_por_pessoa[pessoa] = (p.nome, agora)
            self._salvar()
            mudou = (anterior and anterior[0] != p.nome and agora - anterior[1] < CONVERSA_SEG
                     and p is not self.provedores[0])
            return (TRANSICAO + resposta) if (mudou and TRANSICAO) else resposta
        self._salvar()
        raise SemProvedor(str(ultimo_erro) if ultimo_erro else "SEM_PROVEDOR_DISPONIVEL")


def ler_estado() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}
