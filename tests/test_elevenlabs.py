"""Testes offline da ElevenLabs (rede simulada).

  .\\.venv\\Scripts\\python.exe -m unittest tests.test_elevenlabs -v
"""
from pathlib import Path
import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CHAVE = "sk_" + "a" * 40
C = {"CHAVE": CHAVE, "VOZ": "voz123", "MODELO_VOZ": "eleven_multilingual_v2", "MODELO_STT": "scribe_v2"}


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): return False


class ElevenTests(unittest.TestCase):
    def test_falar_monta_pedido(self):
        from integrations import elevenlabs
        visto = {}

        def abrir(req, timeout):
            visto.update(url=req.full_url, corpo=json.loads(req.data), chave=req.get_header("Xi-api-key"))
            return Resp(b"MP3DATA")

        with mock.patch("urllib.request.urlopen", abrir):
            self.assertEqual(elevenlabs.falar("Olá", C), b"MP3DATA")
        self.assertEqual(visto["url"], "https://api.elevenlabs.io/v1/text-to-speech/voz123?output_format=mp3_44100_128")
        self.assertEqual(visto["corpo"], {"text": "Olá", "model_id": "eleven_multilingual_v2"})
        self.assertEqual(visto["chave"], CHAVE)

    def test_transcrever_multipart(self):
        from integrations import elevenlabs
        visto = {}

        def abrir(req, timeout):
            visto["corpo"] = req.data
            visto["tipo"] = req.get_header("Content-type")
            return Resp(json.dumps({"text": " quais as publicações de hoje ", "language_code": "por"}).encode())

        with mock.patch("urllib.request.urlopen", abrir):
            self.assertEqual(elevenlabs.transcrever(b"AUDIO", c=C), "quais as publicações de hoje")
        self.assertIn("multipart/form-data; boundary=", visto["tipo"])
        for trecho in (b'name="model_id"\r\n\r\nscribe_v2', b'name="language_code"\r\n\r\npor', b"AUDIO"):
            self.assertIn(trecho, visto["corpo"])

    def test_erro_nao_mostra_chave(self):
        from integrations import elevenlabs

        def abrir(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 401, "x", {},
                                         io.BytesIO(b'{"detail": {"status": "quota_exceeded"}}'))

        with mock.patch("urllib.request.urlopen", abrir):
            with self.assertRaises(elevenlabs.ElevenErro) as cm:
                elevenlabs.falar("Olá", C)
        self.assertEqual(str(cm.exception), "HTTP 401 quota_exceeded")
        self.assertNotIn(CHAVE, str(cm.exception))

    def test_vozes(self):
        from integrations import elevenlabs
        dados = {"voices": [{"voice_id": "v1", "name": "Ana", "labels": {"gender": "female", "accent": "brazilian"}},
                            {"voice_id": "", "name": "sem id"}]}
        with mock.patch("urllib.request.urlopen", lambda req, timeout: Resp(json.dumps(dados).encode())):
            self.assertEqual(elevenlabs.vozes(C), [{"id": "v1", "nome": "Ana", "info": "female, brazilian"}])


class ProvedorTests(unittest.TestCase):
    def test_com_chave_usa_elevenlabs_e_mp3_sem_pyav(self):
        from integrations import elevenlabs, voz
        env = {"ELEVENLABS_API_KEY": CHAVE, "ELEVENLABS_VOICE_ID": "voz123",
               "VOZ_PROVEDOR": "", "TRANSCRICAO_PROVEDOR": ""}
        with mock.patch.dict(os.environ, env), \
                mock.patch.object(elevenlabs, "falar", lambda t, c=None: b"MP3"), \
                mock.patch.object(elevenlabs, "transcrever", lambda d, n, m, c=None: "texto ok"), \
                mock.patch.object(voz, "_para_ogg", side_effect=ImportError("sem av")):
            self.assertEqual((voz.provedor_voz(), voz.provedor_transcricao()), ("elevenlabs", "elevenlabs"))
            self.assertTrue(voz.transcricao_disponivel())
            self.assertEqual(voz.transcrever(b"x", ".ogg"), "texto ok")
            self.assertEqual(voz.sintetizar("Olá equipe"), (b"MP3", "audio/mpeg"))
            self.assertIn("ElevenLabs", voz.voz_disponivel())

    def test_escolha_local_respeitada(self):
        from integrations import voz
        env = {"ELEVENLABS_API_KEY": CHAVE, "VOZ_PROVEDOR": "windows", "TRANSCRICAO_PROVEDOR": "local"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual((voz.provedor_voz(), voz.provedor_transcricao()), ("windows", "local"))

    def test_sem_chave_fica_local(self):
        from integrations import voz
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "", "VOZ_PROVEDOR": "", "TRANSCRICAO_PROVEDOR": ""}):
            self.assertEqual((voz.provedor_voz(), voz.provedor_transcricao()), ("windows", "local"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
