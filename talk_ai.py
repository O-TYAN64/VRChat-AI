import os
import sqlite3
import threading

from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak

from whisper import load_model
import sounddevice as sd

# =====================
# 環境設定
# =====================
load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 60))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 8))
AUDIO_INPUT_DEVICE_INDEX = os.getenv("AUDIO_INPUT_DEVICE_INDEX")

if AUDIO_INPUT_DEVICE_INDEX is not None:
    AUDIO_INPUT_DEVICE_INDEX = int(AUDIO_INPUT_DEVICE_INDEX)

WAKE_WORDS = [
    w.strip() for w in os.getenv("WAKE_WORD", "").split(",") if w.strip()
]

print(f"✅ MODEL={MODEL}, PROVIDER={PROVIDER}")
print(f"✅ WAKE_WORDS={WAKE_WORDS}")

# =====================
# persona は起動時に1回読む
# =====================
with open("persona.txt", "r", encoding="utf-8") as f:
    PERSONA_TEXT = f.read()


# =====================
# DB 初期化
# =====================
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT,
    value TEXT,
    importance INTEGER DEFAULT 3,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()


# =====================
# DB操作
# =====================
def save_conversation(role, content):
    cursor.execute(
        "INSERT INTO conversations (role, content) VALUES (?, ?)",
        (role, content),
    )
    conn.commit()


def get_conversation_history():
    cursor.execute("""
    SELECT role, content FROM conversations
    ORDER BY id DESC LIMIT ?
    """, (MAX_HISTORY,))
    return cursor.fetchall()[::-1]


def save_memory(key, value, importance=4):
    cursor.execute("""
    INSERT INTO memories (key, value, importance)
    VALUES (?, ?, ?)
    """, (key, value, importance))
    conn.commit()


def load_memories(limit=5):
    cursor.execute("""
    SELECT key, value FROM memories
    WHERE importance >= 4
    ORDER BY updated_at DESC
    LIMIT ?
    """, (limit,))
    return cursor.fetchall()


# =====================
# System Prompt
# =====================
def build_system_prompt():
    memories = load_memories()
    memory_text = "\n".join([f"- {k}: {v}" for k, v in memories])

    return f"""{PERSONA_TEXT}

# あなたが覚えているユーザー情報（事実）
{memory_text}

上記を前提として、自然で親密に会話してください。
"""


# =====================
# ウェイクワード
# =====================
def extract_wake_text(text: str):
    for w in WAKE_WORDS:
        if w in text:
            cleaned = text.replace(w, "", 1).strip(" 、。！？")
            return True, cleaned
    return False, ""


# =====================
# 記憶抽出 判定（重要）
# =====================
def should_extract_memory(text: str):
    triggers = ["好き", "嫌い", "覚えて", "実は", "は", "です"]
    return any(t in text for t in triggers)


def extract_memory_from_text(user_text):
    prompt = f"""
以下から、長期的に覚えるべき事実があれば1つだけ抽出してください。
なければ NONE と返してください。

発言:
「{user_text}」

形式:
key=value
"""

    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=[{"role": "user", "content": prompt}],
        timeout=15
    )

    text = res["choices"][0]["message"]["content"].strip()

    if text == "NONE" or "=" not in text:
        return None

    key, value = text.split("=", 1)
    return key.strip(), value.strip()


# =====================
# AIチャット
# =====================
def chat(user_text):
    messages = [{"role": "system", "content": build_system_prompt()}]

    for role, content in get_conversation_history():
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        api_base="http://localhost:11434",
        messages=messages,
        timeout=TIMEOUT,
        extra_body={
            "options": {
                "num_ctx": 1024,
                "temperature": 0.5
            }
        }
    )

    return res["choices"][0]["message"]["content"]


# =====================
# speak 非同期
# =====================
def speak_async(text):
    threading.Thread(target=speak, args=(text,), daemon=True).start()


# =====================
# メインループ
# =====================
def start_talk_ai():
    print("🎧 ショコラAI 起動（高速・記憶モード）")
    print("👉 呼びかけ:", " / ".join(WAKE_WORDS))

    while True:
        user_text = transcribe_audio()
        if not user_text:
            continue

        called, clean_text = extract_wake_text(user_text)

        if not called:
            continue

        if not clean_text:
            speak_async("なに？")
            continue

        save_conversation("user", clean_text)

        if should_extract_memory(clean_text):
            memory = extract_memory_from_text(clean_text)
            if memory:
                save_memory(memory[0], memory[1])

        reply = chat(clean_text)
        print("AI:", reply)

        save_conversation("assistant", reply)
        speak_async(reply)