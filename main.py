import os
import sqlite3
from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak   # VOICEVOXなど想定

# =====================
# 環境読み込み
# =====================
load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")          # deepseek-r1:latest
PROVIDER = os.getenv("LITELLM_PROVIDER")    # ollama
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 20))
MAX_HISTORY = int(os.getenv("MAX_HISTORY", 40))

print(f"✅ MODEL={MODEL}, PROVIDER={PROVIDER}")

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
        persona = f.read()
    return persona

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
    )

    return response["choices"][0]["message"]["content"]

# =====================
# メイン：音声会話ループ
# =====================
print("🎧 ショコラAI 音声会話モード（Ctrl+Cで終了）")

while True:
    # 🎤 音声入力
    user_text = transcribe_audio()

    if not user_text:
        continue  # 無音スキップ

    save("user", user_text)

    # 🤖 AI 応答
    reply = chat(user_text)
    print("AI:", reply)
    save("assistant", reply)

    # 🔊 音声出力
    speak(reply)