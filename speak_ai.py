import requests
import os
import tempfile
import sounddevice as sd
import scipy.io.wavfile as wav
import scipy.signal
import numpy as np
import re
from dotenv import load_dotenv

# =====================
# .env 読み込み
# =====================
load_dotenv()

VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://localhost:50021")
AUDIO_OUTPUT_DEVICE_INDEX = os.getenv("AUDIO_OUTPUT_DEVICE_INDEX")
VOICEVOX_SPEAKER_ID = int(os.getenv("VOICEVOX_SPEAKER_ID", 2))

if AUDIO_OUTPUT_DEVICE_INDEX is not None:
    AUDIO_OUTPUT_DEVICE_INDEX = int(AUDIO_OUTPUT_DEVICE_INDEX)

TARGET_SAMPLE_RATE = 48000  # 再生互換性最優先

# =====================
# 再生処理
# =====================
def play_wav_compatible(path):
    rate, data = wav.read(path)

    # ステレオ → モノラル
    if data.ndim > 1:
        data = data[:, 0]

    # int16 → float32（音量正規化）
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
# テキスト整形
# =====================
def sanitize_text(text: str) -> str:
    NG_CHARS = "（）()[]{}<>"
    for c in NG_CHARS:
        text = text.replace(c, "")
    text = re.sub(r"[\r\n\t]", " ", text)  # 改行・タブ除去
    return text[:300]  # 長さ制限

# =====================
# メイン関数
# =====================
def speak(text: str, speaker: int = VOICEVOX_SPEAKER_ID):
    try:
        text = sanitize_text(text.strip())
        if not text:
            return

        # audio_query
        query_resp = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker},
            timeout=5
        )
        query_resp.raise_for_status()
        query_data = query_resp.json()

        # ★パラメータ上書きで安定化
        query_data['outputSamplingRate'] = 48000
        query_data['outputStereo'] = False

        # synthesis
        audio_resp = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker},
            headers={"Content-Type": "application/json"},
            json=query_data,
            timeout=10
        )
        audio_resp.raise_for_status()

        wav_path = "output.wav"
        with open(wav_path, "wb") as f:
            f.write(audio_resp.content)

        play_wav_compatible(wav_path)

    except requests.exceptions.RequestException as e:
        print("VOICEVOXリクエストエラー:", e)
    except Exception as e:
        print("VOICEVOXその他エラー:", e)