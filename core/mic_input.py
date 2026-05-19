import os
import sounddevice as sd
import numpy as np
import scipy.signal
from math import gcd
from dotenv import load_dotenv
from core.whisper_wrapper import get_whisper_model

# =====================
# .env 読み込み
# =====================
load_dotenv()

AUDIO_INPUT_DEVICE_INDEX = os.getenv("AUDIO_INPUT_DEVICE_INDEX")

if AUDIO_INPUT_DEVICE_INDEX:
    AUDIO_INPUT_DEVICE_INDEX = int(AUDIO_INPUT_DEVICE_INDEX)

_samplerate: int | None = None


def _get_samplerate() -> int:
    global _samplerate
    if _samplerate is None:
        device_info = sd.query_devices(AUDIO_INPUT_DEVICE_INDEX, 'input')
        _samplerate = int(device_info['default_samplerate'])
    return _samplerate


# =====================
# 録音
# =====================
def record_audio(duration=5):
    print("🎤 録音中...")

    samplerate = _get_samplerate()

    print(f"使用サンプルレート: {samplerate}")

    audio = sd.rec(
        int(duration * samplerate),
        samplerate=samplerate,
        channels=1,
        device=AUDIO_INPUT_DEVICE_INDEX
    )

    sd.wait()
    return audio, samplerate


def _to_whisper_array(audio: np.ndarray, sr: int) -> np.ndarray:
    """float32 [-1, 1] に変換し、16kHz にリサンプリングする"""
    data = audio.flatten()
    if data.dtype != np.float32:
        data = data.astype(np.float32) / 32768.0
    if sr != 16000:
        g = gcd(sr, 16000)
        data = scipy.signal.resample_poly(data, 16000 // g, sr // g)
    return data


# =====================
# 音声認識
# =====================
def transcribe_audio():
    audio, sr = record_audio()
    audio_16k = _to_whisper_array(audio, sr)

    segments, info = get_whisper_model().transcribe(
        audio_16k,
        language="ja",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=800)
    )

    text = ""
    for seg in segments:
        if seg.avg_logprob is not None and seg.avg_logprob < -1.0:
            continue
        text += seg.text

    text = text.strip()

    # 短すぎる or 幻聴対策
    if len(text) < 3:
        return ""

    BAN_TEXTS = ["最後まで", "ご視聴ありがとうございました"]
    if any(b in text for b in BAN_TEXTS):
        return ""

    return text