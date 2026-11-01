"""Le uma chave sem mostra-la na tela. Se a colagem falhar (campo vazio), le da
area de transferencia do Windows e depois a limpa."""
from __future__ import annotations

import getpass
import subprocess


def _clipboard() -> str:
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _limpar_clipboard() -> None:
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ' '"],
                       capture_output=True, timeout=15, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def ler_chave(rotulo: str) -> str:
    print(f"1) Copie a {rotulo} (Ctrl+C no site).")
    print("2) Aqui, clique com o botao DIREITO para colar e aperte Enter.")
    print("   (Se nao conseguir colar, apenas aperte Enter: eu leio o que voce copiou.)")
    chave = getpass.getpass("Chave (nao aparece na tela): ").strip()
    if not chave:
        chave = _clipboard()
        if chave:
            print(f"Chave lida da area de transferencia ({len(chave)} caracteres).")
            _limpar_clipboard()
    return chave.strip()
