import os
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak

# =====================
# 環境設定
# =====================
load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 120))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 20))

WAKE_WORDS = [
    w.strip() for w in os.getenv("WAKE_WORD", "").split(",") if w.strip()
]

print(f"✅ MODEL={MODEL}, PROVIDER={PROVIDER}")
print(f"✅ WAKE_WORDS={WAKE_WORDS}")

# =====================
# DB 初期化
# =====================
conn = sqlite3.connect("memory.db")
cursor = conn.cursor()

# 会話ログ（短期記憶）
cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 人間的な記憶（長期記憶）
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


def save_memory(key, value, importance=3):
    cursor.execute("""
    INSERT INTO memories (key, value, importance)
    VALUES (?, ?, ?)
    """, (key, value, importance))
    conn.commit()


def load_memories(limit=10):
    cursor.execute("""
    SELECT key, value FROM memories
    ORDER BY importance DESC, updated_at DESC
    LIMIT ?
    """, (limit,))
    return cursor.fetchall()

# =====================
# プロンプト構築（人格＋記憶）
# =====================
def build_system_prompt():
    # 人格
    with open("persona.txt", "r", encoding="utf-8") as f:
        persona = f.read()

    # 記憶
    memories = load_memories()
    memory_text = "\n".join([f"- {k}: {v}" for k, v in memories])

    return f"""
{persona}

# あなたが覚えているユーザー情報（事実として扱う）
{memory_text}

上記を前提として、親密で自然に、人間のように会話してください。
"""

# =====================
# ウェイクワード判定
# =====================
def extract_wake_text(text: str):
    for w in WAKE_WORDS:
        if w in text:
            cleaned = text.replace(w, "", 1).strip(" 、。！？")
            return True, cleaned
    return False, ""

# =====================
# 記憶抽出（超重要）
# =====================
def extract_memory_from_text(user_text):
    prompt = f"""
以下の発言から、長期的に覚えるべき情報があれば1つだけ抽出してください。
なければ NONE とだけ返してください。

発言:
「{user_text}」

形式:
key=value
"""

    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=[{"role": "user", "content": prompt}],
        timeout=30
    )

    text = res["choices"][0]["message"]["content"].strip()

    if text == "NONE":
        return None

    if "=" not in text:
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
                "num_ctx": 2048,
                "temperature": 0.7
            }
        }
    )

    return res["choices"][0]["message"]["content"]

# =====================
# メインループ
# =====================
print("🎧 ショコラAI 起動（記憶する会話モード）")
print("👉 呼びかけ例:", " / ".join(WAKE_WORDS))

while True:
    user_text = transcribe_audio()
    if not user_text:
        continue

    called, clean_text = extract_wake_text(user_text)

    if not called:
        print("🔕 未呼び出し:", user_text)
        continue

    if not clean_text:
        speak("なに？")
        continue

    # 保存
    save_conversation("user", clean_text)

    # 記憶抽出
    memory = extract_memory_from_text(clean_text)
    if memory:
        save_memory(memory[0], memory[1], importance=4)

    # 応答
    reply = chat(clean_text)
    print("AI:", reply)

    save_conversation("assistant", reply)
    speak(reply)