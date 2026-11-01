from dataclasses import dataclass
import re


class Blocked(RuntimeError):
    pass


class Paused(Blocked):
    pass


class UnknownOutcome(Blocked):
    """External action may have succeeded. Reconcile; never blindly retry."""


AUTO = frozenset({"agenda", "consulta_publica", "resumo", "guia", "documento",
                  "drive", "retorno_integra", "concluir_preparacao", "aviso_interno"})
FORBIDDEN = frozenset({"protocolar", "assinar", "pagar", "decisao_juridica",
                       "credencial_advogado", "certificado", "enviar_cliente"})


def cnj(value: str) -> str:
    if not re.fullmatch(r"[0-9.\-]+", value):
        raise Blocked("CNJ_INVALIDO")
    digits = value.replace(".", "").replace("-", "")
    if len(digits) != 20:
        raise Blocked("CNJ_INVALIDO")
    # Resolução CNJ 65: NNNNNNN-DD.AAAA.J.TR.OOOO, ISO 7064 mod 97-10.
    base = digits[:7] + digits[9:] + "00"
    if int(digits[7:9]) != 98 - int(base) % 97:
        raise Blocked("CNJ_DIGITO_INVALIDO")
    return digits


@dataclass(frozen=True)
class Plan:
    action: str
    task_id: str
    process: str

    @classmethod
    def from_llm(cls, payload: dict, task_id: str, process: str):
        # Only a classification. No arbitrary URLs, selectors, code, recipients,
        # financial amounts or commands are accepted from the model.
        if set(payload) != {"action"} or payload["action"] not in AUTO:
            raise Blocked("PLANO_LLM_INVALIDO")
        return cls(payload["action"], task_id, cnj(process))


def enforce(store, action: str):
    # Technical prohibitions cannot be overridden by approval in this MVP.
    if action in FORBIDDEN or action not in AUTO:
        raise Blocked("ACAO_PROIBIDA_MVP")
    control = store.control()
    if control["paused"]:
        raise Paused("AGENTE_PAUSADO")
    if control["mode"] == "erro":
        raise Blocked("AGENTE_EM_ERRO")
    if store.requires_review(action):
        raise Blocked("AGUARDANDO_APROVACAO")
