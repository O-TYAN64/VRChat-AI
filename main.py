import os
import sqlite3
from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak

# =====================
# 環境読み込み
# =====================
load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 120))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 40))

# ✅ Wake Word（.env から）
WAKE_WORDS = [
    w.strip() for w in os.getenv("WAKE_WORD", "").split(",") if w.strip()
]

print(f"✅ MODEL={MODEL}, PROVIDER={PROVIDER}")
print(f"✅ WAKE_WORDS={WAKE_WORDS}")

# =====================
# DB
# =====================
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT
)
""")
conn.commit()

def save(role, text):
    cursor.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)",
        (role, text),
    )
    conn.commit()

def get_history():
    cursor.execute(
        "SELECT role, content FROM conversations ORDER BY id DESC LIMIT ?",
        (MAX_HISTORY,),
    )
    return cursor.fetchall()[::-1]

# =====================
# プロンプト
# =====================
def build_system_prompt():
    with open("persona.txt", "r", encoding="utf-8") as f:
        return f.read()

# =====================
# ウェイクワード処理
# =====================
def extract_wake_text(text: str):
    """
    ウェイクワードが含まれていれば
    (True, ウェイクワード除去後テキスト)
    含まれなければ (False, "")
    """
    for w in WAKE_WORDS:
        if w in text:
            cleaned = text.replace(w, "", 1).strip(" 、。！？")
            return True, cleaned
    return False, ""

# =====================
# AI
# =====================
def chat(user_text):
    messages = [{"role": "system", "content": build_system_prompt()}]

    for role, content in get_history():
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    response = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        api_base="http://localhost:11434",
        messages=messages,
        timeout=TIMEOUT,
        extra_body={
            "options": {
                "num_ctx": 2048,
                "temperature": 0.7
            }
        }
    )

    return response["choices"][0]["message"]["content"]

# =====================
# メイン：音声会話ループ（Wake Word対応）
# =====================
print("🎧 ショコラAI 音声会話モード（ウェイクワード対応）")
print("👉 呼びかけ例:", " / ".join(WAKE_WORDS))

while True:
    # 🎤 音声入力
    user_text = transcribe_audio()
    if not user_text:
        continue

    # ✅ ウェイクワード判定
    called, clean_text = extract_wake_text(user_text)

    if not called:
        print("🔕 呼びかけ無し:", user_text)
        continue

    # 「ショコラ」だけ言われた場合
    if not clean_text:
        speak("なに？")
        continue

    user_text = clean_text
    save("user", user_text)

    # 🤖 AI 応答
    reply = chat(user_text)
    print("AI:", reply)
    save("assistant", reply)

    # 🔊 音声出力
    speak(reply)