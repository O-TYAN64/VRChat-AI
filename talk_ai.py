import os
import sqlite3
import threading
from datetime import datetime, timedelta

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
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 60))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 8))

WAKE_WORDS = [
    w.strip() for w in os.getenv("WAKE_WORD", "").split(",") if w.strip()
]

print(f"✅ MODEL={MODEL}, PROVIDER={PROVIDER}")
print(f"✅ WAKE_WORDS={WAKE_WORDS}")

# =====================
# persona
# =====================
with open("persona.txt", "r", encoding="utf-8") as f:
    PERSONA_TEXT = f.read()

# =====================
# DB 初期化
# =====================
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

# 会話履歴
cursor.execute("""
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT,
    content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 短期記憶（STM）
cursor.execute("""
CREATE TABLE IF NOT EXISTS short_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    access_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
)
""")

# 長期記憶（LTM）
cursor.execute("""
CREATE TABLE IF NOT EXISTS long_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT,
    value TEXT,
    importance INTEGER DEFAULT 5,
    created_at TEXT NOT NULL
)
""")

conn.commit()

# =====================
# 会話履歴
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

# =====================
# 短期記憶（STM）
# =====================
def add_short_memory(text):
    cursor.execute("""
        INSERT INTO short_memory (content, created_at)
        VALUES (?, ?)
    """, (text, datetime.now().isoformat()))
    conn.commit()

def reinforce_short_memory():
    cursor.execute("""
        UPDATE short_memory
        SET access_count = access_count + 1
    """)
    conn.commit()

# =====================
# 長期記憶（LTM）
# =====================
def save_long_memory(key, value, importance=5):
    cursor.execute("""
        INSERT INTO long_memory (key, value, importance, created_at)
        VALUES (?, ?, ?, ?)
    """, (key, value, importance, datetime.now().isoformat()))
    conn.commit()

def load_long_memories(limit=5):
    cursor.execute("""
        SELECT key, value
        FROM long_memory
        WHERE importance >= 4
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))
    return cursor.fetchall()

# =====================
# System Prompt
# =====================
def build_system_prompt():
    memories = load_long_memories()
    memory_text = "\n".join([f"- {k}: {v}" for k, v in memories])

    return f"""{PERSONA_TEXT}

# あなたが長期的に覚えているユーザー情報
{memory_text}

これらを前提に、自然で親密に会話してください。
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
# 記憶抽出（LLM）
# =====================
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
# 記憶の固定化（STM → LTM）
# =====================
def consolidate_memory(min_access=3, max_age_minutes=10):
    cursor.execute("""
        SELECT id, content, access_count, created_at
        FROM short_memory
    """)
    rows = cursor.fetchall()
    now = datetime.now()

    for mem_id, content, access, created_at in rows:
        age = now - datetime.fromisoformat(created_at)
        if access >= min_access or age > timedelta(minutes=max_age_minutes):
            memory = extract_memory_from_text(content)
            if memory:
                key, value = memory
                save_long_memory(key, value, importance=access)
            cursor.execute("DELETE FROM short_memory WHERE id=?", (mem_id,))
    conn.commit()

# =====================
# チャット
# =====================
def chat(user_text):
    messages = [{"role": "system", "content": build_system_prompt()}]

    for role, content in get_conversation_history():
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=messages,
        timeout=TIMEOUT,
        extra_body={"options": {"temperature": 0.5}}
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
    print("🎧 ショコラAI 起動（STM / LTM 記憶モデル）")

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

        # 短期記憶に追加
        add_short_memory(clean_text)
        reinforce_short_memory()

        reply = chat(clean_text)

        save_conversation("assistant", reply)
        speak_async(reply)

        # 記憶の整理
        consolidate_memory()