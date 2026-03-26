import os
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
from faster_whisper import WhisperModel
import tempfile
from dotenv import load_dotenv

# =====================
# .env 読み込み
# =====================
load_dotenv()

STT_MODEL_SIZE = os.getenv("STT_MODEL_SIZE", "large")
AUDIO_INPUT_DEVICE_INDEX = os.getenv("AUDIO_INPUT_DEVICE_INDEX")

if AUDIO_INPUT_DEVICE_INDEX:
    AUDIO_INPUT_DEVICE_INDEX = int(AUDIO_INPUT_DEVICE_INDEX)

# =====================
# Whisperモデル
# =====================
print(f"Whisper model loading: {STT_MODEL_SIZE}")
model = WhisperModel(STT_MODEL_SIZE)

# =====================
# 録音
# =====================
def record_audio(duration=5):
    print("🎤 録音中...")

    # デバイス情報取得
    device_info = sd.query_devices(AUDIO_INPUT_DEVICE_INDEX, 'input')

    samplerate = int(device_info['default_samplerate'])

    print(f"使用サンプルレート: {samplerate}")

    audio = sd.rec(
        int(duration * samplerate),
        samplerate=samplerate,
        channels=1,
        device=AUDIO_INPUT_DEVICE_INDEX
    )

    sd.wait()
    return audio, samplerate
# =====================
# 保存
# =====================
def save_wav(audio, samplerate):
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    wav.write(temp_file.name, samplerate, audio)
    return temp_file.name

# =====================
# 音声認識
# =====================
def transcribe_audio():
    audio, sr = record_audio()
    wav_path = save_wav(audio, sr)

    segments, info = model.transcribe(
        wav_path,
        language="ja",
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=800)
    )

    text = ""
    for seg in segments:
        if seg.avg_logprob is not None and seg.avg_logprob < -1.0:
            continue
        text += seg.text

    os.remove(wav_path)

    text = text.strip()

    # 短すぎる or 幻聴対策
    if len(text) < 3:
        return ""

    BAN_TEXTS = ["最後まで", "ご視聴ありがとうございました"]
    if any(b in text for b in BAN_TEXTS):
        return ""

    print("You(voice):", text)
    return text