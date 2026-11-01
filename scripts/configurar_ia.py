"""Liga a IA do atendente e escolhe o provedor: Groq (gratuito, nuvem), Ollama (gratuito, neste PC)
ou Claude (pago, lê PDF e fotos). As chaves NÃO aparecem na tela.

Uso: dois cliques em CONFIGURAR_IA.bat
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from configurar_uazapi import atualizar_env as _gravar_env  # noqa: E402


def atualizar_env(valores: dict) -> None:
    _gravar_env(valores)
    os.environ.update(valores)      # deixa a lista de provedores atualizada nesta mesma execucao

try:   # le o .env atual para nao sobrescrever escolhas ja feitas
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

CLAUDE_PADRAO = "claude-sonnet-5-5"
GROQ_PADRAO = "llama-3.3-70b-versatile"
OLLAMA_PADRAO = "qwen2.5:7b"


def _lista(adicionar: str = "", remover: str = "") -> str:
    atual = [x.strip().lower() for x in os.environ.get("IA_PROVEDORES", "").split(",") if x.strip()]
    if not atual:   # instalacoes antigas: so o provedor unico
        atual = [x for x in (os.environ.get("IA_PROVEDOR", "").strip().lower(),) if x]
    if adicionar and adicionar not in atual:
        atual.append(adicionar)
    atual = [x for x in atual if x != remover]
    return ",".join(x for x in ("claude", "groq", "ollama") if x in atual)


def _falha(exc) -> int:
    t = str(exc).lower()
    print(f"\nTeste da IA: FALHOU ({exc}).")
    if "credit" in t or "billing" in t or "balance" in t:
        print("-> Conta SEM CREDITO (a assinatura do Claude.ai NAO inclui credito da API).")
    elif "401" in t or "invalid api key" in t:
        print("-> Chave errada ou apagada. Gere outra e rode de novo.")
    elif "404" in t or "model" in t:
        print("-> Modelo indisponivel. Rode de novo e escolha outro modelo.")
    elif "429" in t or "rate" in t:
        print("-> Limite gratuito atingido no momento. Aguarde alguns minutos.")
    elif "sem_conexao" in t:
        print("-> Sem conexao. No Ollama: confira se o programa Ollama esta aberto (icone perto do relogio).")
    print("RESULTADO=IA_FALHOU (nada foi salvo)")
    return 3


def groq() -> int:
    from _segredo import ler_chave
    from integrations import ia_openai
    print("\nGroq: crie a chave gratis em console.groq.com > API Keys > Create API Key.")
    chave = ler_chave("chave da Groq (comeca com gsk_)")
    if len(chave) < 20 or " " in chave:
        print("ERRO: chave vazia ou invalida.")
        return 2
    print("Modelos sugeridos: 1) llama-3.3-70b-versatile (recomendado)  2) openai/gpt-oss-120b  3) llama-3.1-8b-instant")
    esc = input("Escolha (Enter = 1, ou digite o nome do modelo): ").strip()
    modelo = {"": GROQ_PADRAO, "1": GROQ_PADRAO, "2": "openai/gpt-oss-120b", "3": "llama-3.1-8b-instant"}.get(esc, esc)
    c = {**ia_openai.config("groq"), "CHAVE": chave, "MODELO": modelo}
    try:
        nome = ia_openai.teste_rapido(c)
    except Exception as exc:
        return _falha(exc)
    atualizar_env({"WA_IA_ENABLED": "true", "IA_PROVEDORES": _lista("groq"), "GROQ_API_KEY": chave,
                   "GROQ_MODELO": modelo})
    print(f"\nGroq respondeu ({nome}). Le texto, audio transcrito e PDF com texto; NAO le fotos.")
    return 0


def ollama() -> int:
    from integrations import ia_openai
    base = os.environ.get("OLLAMA_URL", "").strip() or "http://127.0.0.1:11434"
    try:
        instalados = ia_openai.modelos_ollama(base)
    except Exception:
        print("\nNao encontrei o Ollama neste computador.")
        print("1) Baixe e instale em https://ollama.com/download (Windows) e deixe o programa aberto.")
        print(f"2) Baixe um modelo no PowerShell:  ollama pull {OLLAMA_PADRAO}")
        print("3) Rode este configurador de novo.")
        print("RESULTADO=IA_FALHOU (Ollama nao encontrado)")
        return 3
    if not instalados:
        print(f"\nO Ollama esta instalado, mas sem modelos. No PowerShell rode:  ollama pull {OLLAMA_PADRAO}")
        print("Depois rode este configurador de novo.")
        return 3
    print("\nModelos instalados no Ollama:")
    for i, m in enumerate(instalados, 1):
        print(f"  {i}) {m}")
    esc = input("Numero do modelo (Enter = 1): ").strip() or "1"
    if not esc.isdigit() or not 1 <= int(esc) <= len(instalados):
        print("ERRO: numero invalido.")
        return 2
    modelo = instalados[int(esc) - 1]
    visao = input("Esse modelo le imagens (ex.: modelos 'vl'/'vision')? (s/N): ").strip().lower() in ("s", "sim")
    c = {**ia_openai.config("ollama"), "MODELO": modelo, "VISAO": visao}
    print("Testando (no primeiro uso o modelo e carregado na memoria; pode levar 1 minuto)...")
    try:
        nome = ia_openai.teste_rapido(c)
    except Exception as exc:
        return _falha(exc)
    atualizar_env({"WA_IA_ENABLED": "true", "IA_PROVEDORES": _lista("ollama"), "OLLAMA_URL": base,
                   "OLLAMA_MODELO": modelo, "IA_VISAO": "true" if visao else "false"})
    print(f"\nOllama respondeu ({nome}). Tudo roda neste computador: nada sai daqui.")
    return 0


def claude() -> int:
    from _segredo import ler_chave
    from integrations import ia_claude
    chave = ler_chave("chave da Anthropic (comeca com sk-ant-)")
    if len(chave) < 20 or " " in chave:
        print("ERRO: chave vazia ou invalida.")
        return 2
    modelo = input(f"Modelo (Enter = {CLAUDE_PADRAO}): ").strip() or CLAUDE_PADRAO
    try:
        nome = ia_claude.teste_rapido({"ATIVA": True, "CHAVE": chave, "MODELO": modelo, "MAX_TOKENS": 1024})
    except Exception as exc:
        return _falha(exc)
    atualizar_env({"WA_IA_ENABLED": "true", "IA_PROVEDORES": _lista("claude"), "ANTHROPIC_API_KEY": chave,
                   "IA_MODELO": modelo, "IA_MAX_TOKENS": "1024"})
    print(f"\nClaude respondeu ({nome}). Le texto, PDF e fotos.")
    return 0


def main() -> int:
    print("Configuracao da IA do assistente juridico. As chaves NAO aparecem na tela.")
    print("Voce pode configurar MAIS DE UM: o robo usa Claude > Groq > Ollama e troca sozinho se um falhar.\n")
    atual = _lista()
    print(f"Configurados hoje: {atual.replace(',', ' > ') if atual else 'nenhum'}\n")
    print("  1) Groq   - gratuito, na nuvem, rapido (texto e PDF com texto)")
    print("  2) Ollama - gratuito, roda NESTE computador (sigilo total; mais lento)")
    print("  3) Claude - pago (creditos da API), le PDF e fotos")
    print("  4) Remover um provedor da lista")
    print("  5) Desligar a IA")
    esc = input("Escolha (1-5): ").strip()
    if esc == "5":
        atualizar_env({"WA_IA_ENABLED": "false"})
        print("RESULTADO=IA_DESLIGADA - reinicie o atendente")
        return 0
    if esc == "4":
        nome = input("Qual remover? (claude, groq ou ollama): ").strip().lower()
        nova = _lista(remover=nome)
        atualizar_env({"IA_PROVEDORES": nova})
        print(f"Lista agora: {nova.replace(',', ' > ') or 'nenhum'}")
        print("RESULTADO=IA_ATUALIZADA - reinicie o atendente")
        return 0
    rc = {"1": groq, "2": ollama, "3": claude}.get(esc, lambda: (print("Opcao invalida."), 2)[1])()
    if rc == 0:
        print(f"Ordem de uso: {_lista().replace(',', ' > ')} (rode de novo para acrescentar outro provedor)")
        print("RESULTADO=IA_CONFIGURADA - reinicie o atendente (INICIAR_ATENDENTE.bat)")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
