"""Grava a configuracao da UazAPI no .env sem mostrar o token na tela.

O token e digitado/colado pelo proprio usuario (entrada oculta). Nada e enviado
para fora alem do teste de status na propria UazAPI.

Uso:
  & ".\\.venv\\Scripts\\python.exe" .\\scripts\\configurar_uazapi.py
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
ENV = ROOT / ".env"

FIXOS = {
    "WA_PROVIDER": "uazapi",
    "WA_INTEGRA_ENABLED": "true",
    "WA_ATENDENTE_ENABLED": "true",
    "WA_RECIPIENTS_FILE": "var/whatsapp-recipients.json",
    "WA_INCLUIR_PARTES": "false",
}


def atualizar_env(valores: dict[str, str]) -> None:
    linhas = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    pendentes = dict(valores)
    saida = []
    for ln in linhas:
        m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)\s*=", ln)
        if m and m.group(1) in valores:
            if m.group(1) in pendentes:      # 1a ocorrencia: atualiza
                saida.append(f"{m.group(1)}={pendentes.pop(m.group(1))}")
            # ocorrencias repetidas da mesma chave sao removidas (a ultima "venceria" a nova)
        else:
            saida.append(ln)
    if pendentes:
        saida += ["", "# --- WhatsApp / UazAPI ---"] + [f"{k}={v}" for k, v in pendentes.items()]
    tmp = ENV.with_suffix(".tmp")
    tmp.write_text("\n".join(saida) + "\n", encoding="utf-8")
    os.replace(tmp, ENV)


def explicar_falha(exc, url) -> int:
    import urllib.error
    host = url.split("//", 1)[1]
    if isinstance(exc, urllib.error.HTTPError):
        cod = exc.code
        print(f"Teste de status: FALHOU (HTTP {cod}) no servidor {host}")
        if cod in (401, 403):
            print("-> TOKEN recusado. Use o token da INSTANCIA do numero do robo (nao o admintoken)")
            print("   e confira se ele e da mesma instancia/servidor do endereco informado.")
        elif cod in (301, 302, 303, 307, 308, 404, 405):
            print("-> ENDERECO errado: esse endereco nao e o servidor da API da sua instancia.")
            print("   No painel da UazAPI, copie o campo 'Server URL' / 'URL da API' (ex.: https://nome.uazapi.com).")
        else:
            print("-> Erro no servidor da UazAPI. Tente de novo em alguns minutos.")
    else:
        print(f"Teste de status: FALHOU ({type(exc).__name__}) no servidor {host}")
        print("-> Servidor nao encontrado ou sem internet. Confira o endereco.")
    print("RESULTADO=FALHA_CONEXAO  (o .env foi salvo; rode este comando de novo com os dados corrigidos)")
    return 3


def main() -> int:
    print("Configuracao da UazAPI (numero do robo). O token NAO aparece na tela.\n")
    url = input("Endereco do servidor (ex.: https://escritorio.uazapi.com): ").strip().rstrip("/")
    if not re.fullmatch(r"https://[A-Za-z0-9.-]+(:\d+)?", url):
        print("ERRO: use so o endereco do SERVIDOR da API, ex.: https://nome.uazapi.com")
        print("      (sem nada depois do .com: sem /interno, sem ?p=..., sem barra no final).")
        return 2
    if url.split("//", 1)[1].lower() in ("uazapi.dev", "www.uazapi.dev", "uazapi.com", "www.uazapi.com", "docs.uazapi.com"):
        print("ERRO: esse e o endereco do SITE/painel da UazAPI, nao do servidor da sua instancia.")
        print("      No painel, procure o campo 'Server URL' / 'URL da API' (ex.: https://nome.uazapi.com).")
        return 2
    token = getpass.getpass("Token da INSTANCIA (cole com clique direito e aperte Enter): ").strip()
    if len(token) < 8 or " " in token:
        print("ERRO: token vazio ou invalido. Use o token da instancia (nao o admintoken).")
        return 2
    atualizar_env({**FIXOS, "UAZAPI_URL": url, "UAZAPI_TOKEN": token})
    print(f"\n.env atualizado (token com {len(token)} caracteres, final ...{token[-3:]}).")

    os.environ.update({"UAZAPI_URL": url, "UAZAPI_TOKEN": token})
    from integrations import uazapi
    try:
        st = uazapi.status()
    except Exception as exc:  # nao imprime token
        return explicar_falha(exc, url)
    print(f"Status da instancia: {st}")
    print("RESULTADO=" + ("CONECTADO" if st == "connected" else "NUMERO_DESCONECTADO"))
    return 0 if st == "connected" else 4


if __name__ == "__main__":
    raise SystemExit(main())
