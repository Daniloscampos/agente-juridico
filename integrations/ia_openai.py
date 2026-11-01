"""IA via API compatÃ­vel com OpenAI: Groq (nuvem, gratuito) e Ollama (local, no prÃ³prio PC).

Mesma persona, mesmas ferramentas de CONSULTA e mesmas regras do Claude (ia_persona.py /
ia_claude.FERRAMENTAS). Nenhuma ferramenta de escrita existe.

.env:
  IA_PROVEDOR=groq | ollama | claude
  GROQ_API_KEY=...            (console.groq.com > API Keys)
  GROQ_MODELO=llama-3.3-70b-versatile
  OLLAMA_URL=http://127.0.0.1:11434
  OLLAMA_MODELO=qwen2.5:7b
Imagens: sÃ³ com modelo que aceite visÃ£o (IA_VISAO=true). PDFs: o texto Ã© extraÃ­do no PC (pypdf).
"""
from __future__ import annotations

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
import base64
import io
import json
import os
import urllib.error
import urllib.request

MAX_RODADAS = 5
MAX_RESULTADO = 12000
MAX_TEXTO_PDF = 30000
GROQ_URL = "https://api.groq.com/openai/v1"


class IAErro(RuntimeError):
    pass


def config(provedor: str | None = None) -> dict:
    p = (provedor or os.environ.get("IA_PROVEDOR", "")).strip().lower() or "groq"
    if p == "gemini":
        return {
            "PROVEDOR": "gemini",
            "URL": "https://generativelanguage.googleapis.com/v1beta/openai",
            "CHAVE": os.environ.get("GEMINI_API_KEY", "").strip(),
            "MODELO": os.environ.get("GEMINI_MODELO", "gemini-3.5-flash-lite"),
            "VISAO": False,
            "TIMEOUT": 90
        }
    if p == "ollama":
        base = (os.environ.get("OLLAMA_URL", "").strip() or "http://127.0.0.1:11434").rstrip("/")
        return {"PROVEDOR": "ollama", "URL": base + "/v1", "CHAVE": "ollama",
                "MODELO": os.environ.get("OLLAMA_MODELO", "").strip() or "qwen2.5:7b",
                "VISAO": os.environ.get("IA_VISAO", "").strip().lower() == "true", "TIMEOUT": 240, "MAX_PDF": 6000}
    return {"PROVEDOR": "groq", "URL": GROQ_URL, "CHAVE": os.environ.get("GROQ_API_KEY", "").strip(),
            "MODELO": os.environ.get("GROQ_MODELO", "").strip() or "llama-3.3-70b-versatile",
            "VISAO": os.environ.get("IA_VISAO", "").strip().lower() == "true", "TIMEOUT": 90}


def problemas(c: dict) -> list[str]:
    if c["PROVEDOR"] == "groq" and (len(c["CHAVE"]) < 20 or " " in c["CHAVE"]):
        return ["GROQ_API_KEY vazia/invalida (rode CONFIGURAR_IA.bat)"]
    return []


def _post(payload: dict, c: dict) -> dict:
    req = urllib.request.Request(c["URL"] + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                 method="POST", headers={"Authorization": f"Bearer {c['CHAVE']}",
                                                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=c.get("TIMEOUT", 90)) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as exc:      # so codigo e mensagem curta (nunca a chave)
        try:
            erro = json.loads(exc.read() or b"{}").get("error") or {}
            msg = str(erro.get("message", "") if isinstance(erro, dict) else erro)[:160]
        except Exception:
            msg = ""
        raise IAErro(f"HTTP {exc.code}" + (f": {msg}" if msg else "")) from None
    except urllib.error.URLError as exc:
        raise IAErro(f"SEM_CONEXAO ({type(exc.reason).__name__})") from None


def modelos_ollama(base: str = "") -> list[str]:
    base = (base or os.environ.get("OLLAMA_URL", "") or "http://127.0.0.1:11434").rstrip("/")
    with urllib.request.urlopen(base + "/api/tags", timeout=10) as r:
        return [m.get("name", "") for m in json.loads(r.read()).get("models", []) if m.get("name")]


def ferramentas_openai() -> list[dict]:
    from integrations.ia_claude import FERRAMENTAS
    return [{"type": "function", "function": {"name": f["name"], "description": f["description"],
                                              "parameters": f["input_schema"]}} for f in FERRAMENTAS]


def texto_do_pdf(b64: str, limite: int = MAX_TEXTO_PDF) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        raise IAErro("PDF_SEM_LEITOR (instale: .venv\\Scripts\\python.exe -m pip install pypdf)") from None
    leitor = PdfReader(io.BytesIO(base64.b64decode(b64)))
    texto = "\n".join((p.extract_text() or "") for p in leitor.pages).strip()
    if not texto:
        raise IAErro("PDF_SEM_TEXTO (documento escaneado; envie uma foto legÃ­vel ou use o Claude)")
    if len(texto) > limite:
        return texto[:limite] + "\n[... documento cortado por limite de tamanho; avise que analisou sÃ³ o inÃ­cio ...]"
    return texto


def teste_rapido(c: dict, post=None) -> str:
    resp = (post or _post)({"model": c["MODELO"], "max_tokens": 8,
                            "messages": [{"role": "user", "content": "Responda sÃ³: ok"}]}, c)
    return str(resp.get("model") or c["MODELO"])


def responder(texto: str, ferramentas: dict, imagem: tuple[str, str] | None = None,
              historico: list | None = None, c: dict | None = None, post=None,
              pessoa: str = "", cumprimentar: bool = False, modo: str = "completo") -> str:
    from integrations.ia_persona import montar_system
    c = c or config()
    post = post or _post
    pedido = texto.strip() or "Analise o arquivo enviado."
    conteudo: object = pedido
    if imagem:
        dados, tipo = imagem
        if tipo == "application/pdf":
            pedido = f"{pedido}\n\n[Texto extraÃ­do do PDF enviado]\n{texto_do_pdf(dados, c.get('MAX_PDF', MAX_TEXTO_PDF))}"
            conteudo = pedido
        elif c.get("VISAO"):
            conteudo = [{"type": "text", "text": pedido},
                        {"type": "image_url", "image_url": {"url": f"data:{tipo};base64,{dados}"}}]
        else:
            raise IAErro("SEM_VISAO")
    mensagens = [{"role": "system", "content": montar_system(pessoa, cumprimentar, modo=modo)}]
    mensagens += list(historico or []) + [{"role": "user", "content": conteudo}]
    tools = ferramentas_openai()

    for _ in range(MAX_RODADAS):
        resp = post({"model": c["MODELO"], "messages": mensagens, "tools": tools, "tool_choice": "auto",
                     "temperature": 0.3, "max_tokens": 1200}, c)
        escolha = (resp.get("choices") or [{}])[0]
        msg = escolha.get("message") or {}
        chamadas = msg.get("tool_calls") or []
        if not chamadas:
            final = (msg.get("content") or "").strip()
            if not final:
                raise IAErro("RESPOSTA_VAZIA")
            return final
        mensagens.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": chamadas})
        for ch in chamadas:
            fn_info = ch.get("function") or {}
            nome = fn_info.get("name")
            try:
                args = json.loads(fn_info.get("arguments") or "{}") or {}
                fn = ferramentas.get(nome)
                if fn is None:
                    raise IAErro("FERRAMENTA_DESCONHECIDA")
                saida = json.dumps(fn(**args), ensure_ascii=False)[:MAX_RESULTADO]
            except Exception as exc:
                saida = json.dumps({"erro": f"Falha na consulta ({type(exc).__name__}). "
                                            "Não significa que não há publicações."}, ensure_ascii=False)
            mensagens.append({"role": "tool", "tool_call_id": ch.get("id", ""), "content": saida})
    raise IAErro("LIMITE_DE_CONSULTAS")

