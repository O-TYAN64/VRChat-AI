import requests
import os
import tempfile
import sounddevice as sd
import scipy.io.wavfile as wav
import scipy.signal
import numpy as np
import re
from dotenv import load_dotenv
from core.text_utils import strip_action_brackets

# =====================
# .env 読み込み
# =====================
load_dotenv()

GPT_SOVITS_URL = os.getenv("GPT_SOVITS_URL", "http://127.0.0.1:9880")
REF_AUDIO_PATH = os.getenv("GPT_SOVITS_REF_AUDIO", "ref.wav")
TEXT_LANG = os.getenv("GPT_SOVITS_TEXT_LANG", "ja")
PROMPT_LANG = os.getenv("GPT_SOVITS_PROMPT_LANG", "ja")

AUDIO_OUTPUT_DEVICE_INDEX = os.getenv("AUDIO_OUTPUT_DEVICE_INDEX")
if AUDIO_OUTPUT_DEVICE_INDEX is not None:
    AUDIO_OUTPUT_DEVICE_INDEX = int(AUDIO_OUTPUT_DEVICE_INDEX)

TARGET_SAMPLE_RATE = 48000  # VRChat / Windows 安定用

# =====================
# WAV 再生（互換性重視）
# =====================
def play_wav_compatible(path: str):
    rate, data = wav.read(path)

    # ステレオ → モノラル
    if data.ndim > 1:
        data = data[:, 0]

    # int16 → float32
    if data.dtype != np.float32:
        data = data.astype(np.float32) / 32768.0

    # サンプルレート変換
    if rate != TARGET_SAMPLE_RATE:
        num_samples = int(len(data) * TARGET_SAMPLE_RATE / rate)
        data = scipy.signal.resample(data, num_samples)
        rate = TARGET_SAMPLE_RATE

    sd.play(
        data,
        samplerate=rate,
        device=AUDIO_OUTPUT_DEVICE_INDEX,
        blocking=True
    )

# =====================
# テキスト整形（SoVITS 安定化）
# =====================
def sanitize_text(text: str) -> str:
    """括弧アクション除去 + SoVITS向け整形（文字数制限・改行除去）"""
    text = strip_action_brackets(text)          # 括弧の中身ごと除去
    text = re.sub(r'[\r\n\t]', ' ', text)    # 改行をスペースに
    return text[:300]

# =====================
# GPT‑SoVITS 音声合成
# =====================
def speak(text: str):
    text = sanitize_text(text.strip())
    if not text:
        return

    payload = {
        "text": text,
        "text_lang": TEXT_LANG,
        "ref_audio_path": REF_AUDIO_PATH,
        "prompt_lang": PROMPT_LANG
    }

    try:
        resp = requests.post(
            f"{GPT_SOVITS_URL}/tts",
            json=payload,
            timeout=30
        )
        resp.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            f.write(resp.content)
            wav_path = f.name

        play_wav_compatible(wav_path)
        os.remove(wav_path)

    except requests.exceptions.RequestException as e:
        print("GPT‑SoVITS 通信エラー:", e)
    except Exception as e:
        print("GPT‑SoVITS 実行エラー:", e)