import cv2
import numpy as np
import time
import ctypes
import sqlite3

import win32gui
import win32ui
import win32con

import pytesseract
import whisper
import sounddevice as sd
from scipy.io.wavfile import write

from ultralytics import YOLO
from datetime import datetime

import tempfile
import os
from dotenv import load_dotenv


# =====================
# 初期設定
# =====================

load_dotenv()

MODEL_PATH = os.getenv("YOLO_MODEL_PATH", "base.pt")
AUDIO_INPUT_DEVICE_INDEX = os.getenv("AUDIO_INPUT_DEVICE_INDEX")

if AUDIO_INPUT_DEVICE_INDEX is not None:
    AUDIO_INPUT_DEVICE_INDEX = int(AUDIO_INPUT_DEVICE_INDEX)

pytesseract.pytesseract.tesseract_cmd = os.getenv(r"PYTESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")

SAMPLE_RATE = 16000
RECORD_SECONDS = 3


# =========================
# Whisper 音声認識
# =========================

print("🔊 Loading Whisper...")
whisper_model = whisper.load_model("base")
print("✅ Whisper ready")


# =========================
# ローカルデータベース
# =========================
os.makedirs("data", exist_ok=True)
conn = sqlite3.connect("data/thinking.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS speeches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    time TEXT,
    speaker TEXT,
    content TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS speaker_profiles (
    speaker TEXT PRIMARY KEY,
    speak_count INTEGER,
    last_spoken TEXT,
    impression TEXT
)
""")

conn.commit()


def save_speech(speaker, content):
    now = datetime.now().isoformat(timespec="seconds")

    cur.execute(
        "INSERT INTO speeches VALUES (NULL, ?, ?, ?)",
        (now, speaker, content)
    )

    # 既存スピーカーデータがあれば更新
    cur.execute(
        "SELECT speak_count FROM speaker_profiles WHERE speaker=?",
        (speaker,)
    )
    row = cur.fetchone()

    if row:
        cur.execute("""
        UPDATE speaker_profiles
        SET speak_count = speak_count + 1,
            last_spoken = ?
        WHERE speaker = ?
        """, (content, speaker))
    else:
        cur.execute("""
        INSERT INTO speaker_profiles
        VALUES (?, 1, ?, ?)
        """, (speaker, content, "初回登録"))

    conn.commit()


# =========================
# VRChat ウィンドウ取得
# =========================

def find_vrchat_window():
    result = []

    def callback(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        if (
            win32gui.GetWindowText(hwnd) == "VRChat"
            and win32gui.GetClassName(hwnd) == "UnityWndClass"
        ):
            result.append(hwnd)

    win32gui.EnumWindows(callback, None)
    return result[0] if result else None


def capture_window(hwnd):
    _, _, w, h = win32gui.GetClientRect(hwnd)
    if w <= 0 or h <= 0:
        return None

    hdc = win32gui.GetWindowDC(hwnd)
    src = win32ui.CreateDCFromHandle(hdc)
    mem = src.CreateCompatibleDC()

    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(src, w, h)
    mem.SelectObject(bmp)

    ctypes.windll.user32.PrintWindow(hwnd, mem.GetSafeHdc(), 2)

    img = np.frombuffer(bmp.GetBitmapBits(True), dtype=np.uint8)
    img.shape = (h, w, 4)
    img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    win32gui.DeleteObject(bmp.GetHandle())
    mem.DeleteDC()
    src.DeleteDC()
    win32gui.ReleaseDC(hwnd, hdc)

    return img


# =========================
# 発話判定＋OCR
# =========================

def is_speaking(roi):
    if roi.size == 0:
        return False
    b, g, r = np.mean(roi.reshape(-1, 3), axis=0)
    return b > 140 and g > 100 and r < 120


def extract_name(roi):
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2)
    _, th = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY)
    text = pytesseract.image_to_string(th, lang="eng", config="--psm 7")

    name = (
        text.strip()
        .split("\n")[0]
        .replace(" ", "")
    )

    return name if len(name) >= 2 else None


def record_and_transcribe():
    audio = sd.rec(
        int(RECORD_SECONDS * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16"
    )
    sd.wait()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        write(f.name, SAMPLE_RATE, audio)
        path = f.name

    result = whisper_model.transcribe(path, language="ja")
    os.remove(path)

    return result["text"].strip()


# =========================
# メイン処理（YOLO 監視ループ）
# =========================

def yolo_run():
    hwnd = find_vrchat_window()
    if not hwnd:
        print("⚠ VRChat window not found")
        return

    model = YOLO(MODEL_PATH)
    cv2.namedWindow("VRC Speaker Listener", cv2.WINDOW_NORMAL)

    last_capture = {}

    print("✅ Observer running")

    while True:
        frame = capture_window(hwnd)
        if frame is None:
            time.sleep(0.1)
            continue

        results = model(frame, conf=0.4, verbose=False)

        for box in results[0].boxes or []:
            if results[0].names[int(box.cls[0])] != "person":
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])

            name_plate = frame[
                max(0, y1 - int((y2 - y1) * 0.4)):y1,
                x1:x2
            ]

            if is_speaking(name_plate):
                name = extract_name(name_plate)
                if not name:
                    continue

                if name not in last_capture or time.time() - last_capture[name] > 3:
                    content = record_and_transcribe()
                    if content:
                        save_speech(name, content)
                        print(f"🗣 {name}: {content}")

                    last_capture[name] = time.time()

                cv2.putText(
                    frame,
                    f"SPEAKING: {name}",
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (255, 200, 0),
                    2,
                )

        cv2.imshow("VRC Speaker Listener", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(0.03)

    cv2.destroyAllWindows()