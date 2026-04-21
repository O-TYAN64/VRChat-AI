import os
import threading
from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak

from memory_system import (
    init_db,
    add_short_memory,
    reinforce_short_memory,
    cleanup_short_memory,
    consolidate_memory,
    decay_long_memory,
    load_long_memories,
)

# =====================
# 環境設定
# =====================
load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 60))

WAKE_WORD_ENABLED = os.getenv("WAKE_WORD_ENABLED", "true").lower() == "true"
WAKE_WORDS = [w.strip() for w in os.getenv("WAKE_WORD", "").split(",") if w.strip()]

PERSONA_TEXT = ""
PERSONA_FILE = os.getenv("PERSONA_FILE")
if PERSONA_FILE and os.path.exists(PERSONA_FILE):
    with open(PERSONA_FILE, "r", encoding="utf-8") as f:
        PERSONA_TEXT = f.read()

print("✅ Wake:", WAKE_WORD_ENABLED, WAKE_WORDS)

# =====================
# 初期化
# =====================
init_db()

# =====================
# System Prompt
# =====================
def build_system_prompt():
    memories = load_long_memories()

    memory_block = ""
    if memories:
        memory_block = "\n".join([f"- {m}" for m in memories])

    return f"""{PERSONA_TEXT}

# 長期記憶（参考情報）
以下は、過去の会話から得たユーザーに関する事実です。
会話の参考にしてくださいが、必ず触れる必要はありません。
{memory_block}
# 会話ルール
- () や 「」 を使って行動や感情の表現をするのは禁止です。あくまで自然な会話を心がけてください。
- 一度に話す量は1〜2文程度が望ましい
- 無理に質問しなくてよい
- 会話が続きそうなときだけ、自然な質問を1つ入れてもよい
# NG行動
- () や 「」 を使って行動や感情の表現をする
- 箇条書きで話す
- 教師のように説明する
- 尋問のように質問し続ける
- 感情のない機械的な返答
# 会話例
ユーザー: 今日はいい天気ですね。
AI: ほんとですね。外に出ると気持ちよさそうですね。
"""

# =====================
# Wake word
# =====================
def extract_wake_text(text: str):
    if not WAKE_WORD_ENABLED or not WAKE_WORDS:
        return True, text.strip()

    for w in WAKE_WORDS:
        if w in text:
            return True, text.replace(w, "", 1).strip(" 、。！？")

    return False, ""

# =====================
# Chat
# =====================
def chat(user_text: str) -> str:
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user_text},
    ]

    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=messages,
        timeout=TIMEOUT,
    )

    return res["choices"][0]["message"]["content"]

# =====================
# Speak
# =====================
def speak_async(text):
    threading.Thread(target=speak, args=(text,), daemon=True).start()

# =====================
# メインループ
# =====================
def start_talk_ai():
    print("🎧 AI 起動")

    while True:
        user_text = transcribe_audio()
        if not user_text:
            continue

        print("[USER]", user_text)

        is_woke, clean_text = extract_wake_text(user_text)
        if not is_woke or not clean_text:
            continue

        # ✅ ユーザー発言を記憶
        add_short_memory("user", clean_text)
        reinforce_short_memory()

        reply = chat(clean_text)
        print("[AI]", reply)

        # ✅ AI発言も記憶
        add_short_memory("assistant", reply)

        speak_async(reply)

        # ✅ 記憶整理
        consolidate_memory()
        cleanup_short_memory()
        decay_long_memory()