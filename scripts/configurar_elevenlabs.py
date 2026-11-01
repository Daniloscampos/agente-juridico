"""Liga a ElevenLabs no atendente: voz natural nas respostas e (opcional) transcricao dos audios.
A chave NAO aparece na tela.

Uso (na pasta do projeto):
  .\\.venv\\Scripts\\python.exe .\\scripts\\configurar_elevenlabs.py

Antes: crie a chave em https://elevenlabs.io > Developers > API Keys (permissoes:
Text to Speech, Speech to Text e Voices: leitura).
"""
from __future__ import annotations

import getpass
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from configurar_uazapi import atualizar_env  # noqa: E402

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass


def main() -> int:
    from integrations import elevenlabs

    print("Configuracao da ElevenLabs (voz do robo). A chave NAO aparece na tela.\n")
    from _segredo import ler_chave
    chave = ler_chave("chave da ElevenLabs (comeca com sk_)")
    c = {"CHAVE": chave, "VOZ": "", "MODELO_VOZ": elevenlabs.MODELO_VOZ_PADRAO,
         "MODELO_STT": elevenlabs.MODELO_STT_PADRAO}
    if not elevenlabs.chave_ok(c):
        print("ERRO: chave vazia ou invalida.")
        return 2
    try:
        lista = elevenlabs.vozes(c)
    except Exception as exc:
        if "401" in str(exc) and "missing_permissions" not in str(exc):
            print(f"Teste da chave: FALHOU ({exc}). A chave esta errada ou foi apagada.")
            print("RESULTADO=ELEVENLABS_FALHOU (nada foi salvo)")
            return 3
        lista = []                     # chave sem permissao de LER vozes: escolhe pelo ID
        print("Aviso: esta chave nao tem permissao para listar vozes (Voices). Sem problema:")
    if lista:
        print("\nVozes da sua conta (as multilingues falam portugues):")
        for i, v in enumerate(lista[:25], 1):
            print(f"  {i:2d}) {v['nome']}" + (f"  [{v['info']}]" if v["info"] else ""))
        escolha = input("Numero da voz (Enter = 1): ").strip() or "1"
        if not escolha.isdigit() or not 1 <= int(escolha) <= min(25, len(lista)):
            print("ERRO: numero invalido.")
            return 2
        c["VOZ"] = lista[int(escolha) - 1]["id"]
    else:
        atual = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        dica = f" (Enter = manter a voz atual {atual[:6]}...)" if atual else ""
        voz_id = input(f"ID da voz (elevenlabs.io > Voices > ... > Copy voice ID){dica}: ").strip() or atual
        if not voz_id or " " in voz_id or len(voz_id) < 10:
            print("ERRO: informe o ID da voz (Voice ID).")
            return 2
        c["VOZ"] = voz_id

    print("\nTranscricao dos audios recebidos:")
    print("  1) ElevenLabs (nao precisa instalar nada; o audio e enviado a ElevenLabs)")
    print("  2) Local no computador (faster-whisper; o audio nao sai daqui)")
    stt = "local" if (input("Escolha (Enter = 1): ").strip() or "1") == "2" else "elevenlabs"

    print("\nTestando a voz...")
    try:
        mp3 = elevenlabs.falar("Olá, equipe. Este é o teste de voz do robô do escritório.", c)
    except Exception as exc:
        print(f"Teste de voz: FALHOU ({exc}).")
        print("-> 401 missing_permissions: ative 'Text to Speech' na chave | 401 quota_exceeded: sem creditos")
        print("RESULTADO=ELEVENLABS_FALHOU (nada foi salvo)")
        return 3
    saida = ROOT / "saida"
    saida.mkdir(exist_ok=True)
    (saida / "teste_voz_elevenlabs.mp3").write_bytes(mp3)
    print(r"Voz OK -> ouca em saida\teste_voz_elevenlabs.mp3")
    if stt == "elevenlabs":
        try:
            print(f'Transcricao do teste: "{elevenlabs.transcrever(mp3, c=c)}"')
        except Exception as exc:
            print(f"Transcricao: FALHOU ({exc}) - ative 'Speech to Text' na chave. Usando transcricao local.")
            stt = "local"

    atualizar_env({"ELEVENLABS_API_KEY": chave, "ELEVENLABS_VOICE_ID": c["VOZ"],
                   "ELEVENLABS_MODELO_VOZ": c["MODELO_VOZ"], "ELEVENLABS_MODELO_STT": c["MODELO_STT"],
                   "VOZ_PROVEDOR": "elevenlabs", "TRANSCRICAO_PROVEDOR": stt,
                   "WA_RESPOSTA_VOZ": "true"})
    print(f"\n.env atualizado (voz ElevenLabs; transcricao: {stt}).")
    print("RESULTADO=ELEVENLABS_CONFIGURADA - reinicie o atendente (INICIAR_ATENDENTE.bat)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
