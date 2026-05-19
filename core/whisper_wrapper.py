from faster_whisper import WhisperModel
import os
from dotenv import load_dotenv

load_dotenv()
STT_MODEL_SIZE = os.getenv("STT_MODEL_SIZE", "large")

_whisper_model = None


def get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        print(f"🔊 Whisper loading: {STT_MODEL_SIZE}")
        _whisper_model = WhisperModel(STT_MODEL_SIZE)
        print("✅ Whisper ready")
    return _whisper_model
