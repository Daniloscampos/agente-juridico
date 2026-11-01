"""Define como o robo chama cada pessoa no WhatsApp (ex.: "Dr. Danilo", "Dra. Ana").

Uso (na pasta do projeto):
  .\\.venv\\Scripts\\python.exe .\\scripts\\definir_tratamento.py danilo "Dr. Danilo"
  .\\.venv\\Scripts\\python.exe .\\scripts\\definir_tratamento.py --listar
Reinicie o atendente depois.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)

if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except Exception:
        pass
    p = argparse.ArgumentParser(description="Forma de tratamento usada pelo robo")
    p.add_argument("usuario", nargs="?")
    p.add_argument("tratamento", nargs="?")
    p.add_argument("--listar", action="store_true")
    a = p.parse_args()
    caminho = Path(os.environ.get("WA_RECIPIENTS_FILE", "var/whatsapp-recipients.json"))
    dados = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else []
    if a.listar or not a.usuario:
        for i in dados:
            print(f"{i['username']:<15} ***{i['phone'][-4:]}  tratamento: {i.get('tratamento') or '(nome do usuario)'}")
        raise SystemExit(0)
    alvo = [i for i in dados if i["username"] == a.usuario]
    if not alvo:
        p.error("Usuario sem numero cadastrado (scripts\\manage_whatsapp.py add ...).")
    tratamento = (a.tratamento or "").strip()
    if not tratamento or len(tratamento) > 40:
        p.error('Informe o tratamento entre aspas, ex.: "Dr. Danilo"')
    alvo[0]["tratamento"] = tratamento
    tmp = caminho.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, caminho)
    print(f"Tratamento de {a.usuario} definido como: {tratamento}. Reinicie o atendente.")
