import os
import threading
from dotenv import load_dotenv
from litellm import completion

from mic_input import transcribe_audio
from speak_ai import speak

from memory_system import (
    init_db,
    save_log,
    extract_stm,
    add_stm,
    consolidate,
    cleanup_stm,
    decay_ltm,
    load_ltm,
)

load_dotenv()

MODEL = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT = float(os.getenv("LLM_TIMEOUT", 60))

PERSONA_TEXT = ""
PERSONA_FILE = os.getenv("PERSONA_FILE")
if PERSONA_FILE and os.path.exists(PERSONA_FILE):
    with open(PERSONA_FILE, "r", encoding="utf-8") as f:
        PERSONA_TEXT = f.read()

# =====================
# ※ 呼びかけ設定
# =====================
WAKE_WORD_ENABLED = os.getenv("WAKE_WORD_ENABLED", "False").lower() == "True"
WAKE_WORDS = os.getenv("WAKE_WORDS", "AIさん,AIちゃん").split(",")


# =====================
# ※ システムプロンプト生成
# =====================
def build_system_prompt():
    memories = load_ltm()
    memory_text = "\n".join([f"- {m}" for m in memories])

    return f"""{PERSONA_TEXT}

# 長期記憶（参考情報）
以下は、過去の会話から得たユーザーに関する事実です。
会話の参考にしてくださいが、必ず触れる必要はありません。
{memory_text}
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
# ※ LLMチャット
# =====================
def chat(text: str) -> str:
    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": text},
        ],
        timeout=TIMEOUT,
    )
    return res["choices"][0]["message"]["content"]


# =====================
# ※ 非同期音声出力
# =====================
def speak_async(text):
    threading.Thread(target=speak, args=(text,), daemon=True).start()


# =====================
# ※ 呼びかけON / OFF制御
# =====================
def handle_wake_control(text: str):
    global WAKE_WORD_ENABLED

    if "呼びかけオフ" in text:
        WAKE_WORD_ENABLED = False
        return "呼びかけをオフにしました。"

    if "呼びかけオン" in text:
        WAKE_WORD_ENABLED = True
        return "呼びかけをオンにしました。"

    return None


# =====================
# ※ 呼びかけ判定
# =====================
def extract_wake_text(text: str):
    if not WAKE_WORD_ENABLED:
        return True, text.strip()

    for w in WAKE_WORDS:
        if w in text:
            return True, text.replace(w, "", 1).strip(" 、。！？")

    return False, ""


# =====================
# ※ メインループ
# =====================
def start_talk_ai():
    init_db()
    print("🎧 AI 起動")

    while True:
        user_text = transcribe_audio()
        if not user_text:
            continue

        print("[USER]", user_text)

        # ※ 呼びかけ制御
        control = handle_wake_control(user_text)
        if control:
            speak_async(control)
            continue

        # ※ Wake判定
        is_woke, clean_text = extract_wake_text(user_text)
        if not is_woke or not clean_text:
            continue

        # ※ 記憶処理
        save_log("user", clean_text)

        for kind, content in extract_stm(clean_text):
            add_stm(kind, content)

        reply = chat(clean_text)

        print("[AI]", reply)
        save_log("assistant", reply)
        speak_async(reply)

        consolidate()
        cleanup_stm()
        decay_ltm()