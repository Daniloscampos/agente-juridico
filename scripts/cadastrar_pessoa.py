"""Cadastra uma pessoa da EQUIPE INTERNA para usar o robo pelo WhatsApp (assistente passo a passo).

Uso: dois cliques em CADASTRAR_PESSOA.bat (ou .\\.venv\\Scripts\\python.exe .\\scripts\\cadastrar_pessoa.py)
Depois de cadastrar, reinicie o atendente (INICIAR_ATENDENTE.bat).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def main() -> int:
    from core.auth import Auth, normalize_username
    from core.store import Store

    print("Cadastro de pessoa da equipe interna (WhatsApp do robo)\n")
    try:
        usuario = normalize_username(input("Nome de usuario (sem espacos, ex.: ana.souza): "))
    except ValueError as exc:
        print(f"ERRO: {exc}")
        return 2
    tratamento = input('Como o robo deve chamar a pessoa (ex.: "Dra. Ana") [Enter = nome]: ').strip()[:40]
    fone = re.sub(r"\D", "", input("Celular com DDD (ex.: 44 99999-8888): "))
    if len(fone) in (10, 11):
        fone = "55" + fone
    if not re.fullmatch(r"55\d{10,11}", fone):
        print("ERRO: numero invalido. Use DDD + numero, ex.: 44 99999-8888.")
        return 2
    robo = re.sub(r"\D", "", os.environ.get("WA_NUMERO_ROBO", ""))
    if robo and fone.endswith(robo[-8:]):
        print("ERRO: esse e o numero do proprio robo. Cadastre o celular da pessoa.")
        return 2
    ok = input("Confirma que a pessoa e da EQUIPE INTERNA e autorizou receber mensagens do robo? (s/n): ")
    if ok.strip().lower() not in ("s", "sim"):
        print("Cadastro cancelado.")
        return 2

    store = Store(os.environ.get("AGENT_DB", "var/operational.sqlite"))
    auth = Auth(store)
    with store.db() as db:
        existe = db.execute("SELECT active FROM users WHERE username=?", (usuario,)).fetchone()
    if existe and not existe[0]:
        print("ERRO: esse usuario existe no painel mas esta DESATIVADO.")
        return 2
    if not existe:
        try:   # senha aleatoria: a pessoa usa so o WhatsApp (painel: manage_users.py reset-password)
            auth.create_user(usuario, secrets.token_urlsafe(18), "reader")
        except (ValueError, sqlite3.IntegrityError) as exc:
            print(f"ERRO ao criar usuario: {exc}")
            return 2
        print(f"Usuario '{usuario}' criado (perfil leitura).")

    caminho = Path(os.environ.get("WA_RECIPIENTS_FILE", "var/whatsapp-recipients.json"))
    dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    if any(i.get("phone") == fone and i.get("username") != usuario for i in dados):
        print("ERRO: esse celular ja esta cadastrado para outra pessoa.")
        return 2
    dados = [i for i in dados if i.get("username") != usuario]
    item = {"username": usuario, "phone": fone, "internal": True, "consent": True}
    if tratamento:
        item["tratamento"] = tratamento
    dados.append(item)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)
    print(f"\nCadastrado: {usuario} (***{fone[-4:]})" + (f", chamado de {tratamento}" if tratamento else ""))
    print(f"Pessoas cadastradas agora: {len(dados)}")
    print("RESULTADO=PESSOA_CADASTRADA - reinicie o atendente (INICIAR_ATENDENTE.bat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
