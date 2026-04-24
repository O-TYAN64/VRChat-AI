import os
import sys
import threading
import argparse
from dotenv import load_dotenv
from litellm import completion

from core.memory_system import (
    init_db,
    save_log,
    load_ltm,
    process_text_to_stm,
    consolidate,
    cleanup_stm,
    decay_ltm,
    load_recent_log,
    get_stats,
)

load_dotenv()

# ─────────────────────────────────────────────
# 設定（.env から読み込み）
# ─────────────────────────────────────────────
MODEL    = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT  = float(os.getenv("LLM_TIMEOUT", 180))

MAX_HISTORY = int(os.getenv("MAX_HISTORY", 40))
LTM_TOP     = 5

# Ollama オプション（MSI Stealth 14 AI Studio 向けデフォルト）
OLLAMA_OPTIONS = {
    "num_gpu":    int(os.getenv("OLLAMA_NUM_GPU",    28)),
    "num_thread": int(os.getenv("OLLAMA_NUM_THREAD", 12)),
    "num_ctx":    int(os.getenv("OLLAMA_NUM_CTX",   1024)),
}

WAKE_WORD_ENABLED = os.getenv("WAKE_WORD_ENABLED", "False").lower() == "true"
WAKE_WORDS        = [w.strip() for w in os.getenv("WAKE_WORD", "えーあい,AI,あい").split(",")]

PERSONA_TEXT = ""
PERSONA_FILE = os.getenv("PERSONA_FILE")
if PERSONA_FILE and os.path.exists(PERSONA_FILE):
    with open(PERSONA_FILE, "r", encoding="utf-8") as f:
        PERSONA_TEXT = f.read()


# ─────────────────────────────────────────────
# システムプロンプト
# ─────────────────────────────────────────────
def build_system_prompt() -> str:
    memories = load_ltm(LTM_TOP)
    memory_text = "\n".join(f"- {m}" for m in memories) if memories else "（まだ記憶はありません）"

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
"""


# ─────────────────────────────────────────────
# LLM 呼び出し（会話履歴付き）
# ─────────────────────────────────────────────
def _build_messages(user_text: str) -> list[dict]:
    """直近の会話履歴 + 今回の入力を messages 形式で返す"""
    history = load_recent_log(MAX_HISTORY)
    messages = []
    for h in history:
        role = "user" if h["role"] == "user" else "assistant"
        messages.append({"role": role, "content": h["content"]})
    messages.append({"role": "user", "content": user_text})
    return messages


def llm_chat(text: str) -> str:
    """LLMに投げて返答を得る"""
    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            *_build_messages(text)[:-1],   # 履歴（最後のuserは下で渡す）
            {"role": "user", "content": text},
        ],
        timeout=TIMEOUT,
        options=OLLAMA_OPTIONS,
    )
    return res["choices"][0]["message"]["content"]


# ─────────────────────────────────────────────
# 記憶メンテナンス（共通）
# ─────────────────────────────────────────────
def run_memory_maintenance(user_text: str, ai_text: str) -> None:
    """STM登録 → LTM昇格 → 期限切れSTM削除 → LTM減衰"""
    process_text_to_stm(user_text)
    process_text_to_stm(ai_text)
    consolidate()
    cleanup_stm()
    decay_ltm()


# ─────────────────────────────────────────────
# ウェイクワード制御
# ─────────────────────────────────────────────
def handle_wake_control(text: str) -> str | None:
    """「呼びかけオン/オフ」コマンドを処理。コマンドでなければ None を返す"""
    global WAKE_WORD_ENABLED
    if "呼びかけオフ" in text:
        WAKE_WORD_ENABLED = False
        return "呼びかけをオフにしました。"
    if "呼びかけオン" in text:
        WAKE_WORD_ENABLED = True
        return "呼びかけをオンにしました。"
    return None


def extract_wake_text(text: str) -> tuple[bool, str]:
    """ウェイクワードが含まれるか確認し、除去したテキストを返す"""
    if not WAKE_WORD_ENABLED:
        return True, text.strip()
    for w in WAKE_WORDS:
        if w in text:
            return True, text.replace(w, "", 1).strip(" 、。！？")
    return False, ""


# ─────────────────────────────────────────────
# 音声モード（メイン）
# ─────────────────────────────────────────────
def _speak_async(text: str) -> None:
    from core.speak_ai import speak
    threading.Thread(target=speak, args=(text,), daemon=True).start()


def voice_loop() -> None:
    from core.mic_input import transcribe_audio

    print("🎧 音声AIモード 起動")
    print(f"   モデル: {MODEL}  / プロバイダ: {PROVIDER}")
    print(f"   ウェイクワード: {'有効 ' + str(WAKE_WORDS) if WAKE_WORD_ENABLED else '無効（常時受付）'}")
    print()

    while True:
        user_text = transcribe_audio()
        if not user_text:
            continue

        print(f"[USER] {user_text}")

        # ウェイクワード制御コマンド
        control = handle_wake_control(user_text)
        if control:
            print(f"[SYS]  {control}")
            _speak_async(control)
            continue

        # ウェイクワード判定
        is_woke, clean_text = extract_wake_text(user_text)
        if not is_woke or not clean_text:
            continue

        save_log("user", clean_text)

        try:
            reply = llm_chat(clean_text)
        except Exception as e:
            print(f"[ERR]  LLMエラー: {e}")
            continue

        print(f"[AI]   {reply}")
        save_log("assistant", reply)
        _speak_async(reply)
        run_memory_maintenance(clean_text, reply)


# ─────────────────────────────────────────────
# テキストモード（--text オプション時）
# ─────────────────────────────────────────────
def text_loop() -> None:
    print("=" * 50)
    print("  テキストモード（終了: /quit）")
    print("=" * 50)
    stats = get_stats()
    print(f"  DB状態 → ログ: {stats['log']}件 / STM: {stats['stm']}件 / LTM: {stats['ltm']}件")
    print(f"  モデル: {MODEL}  / プロバイダ: {PROVIDER}")
    print()

    while True:
        try:
            user_input = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n終了します。")
            break

        if not user_input:
            continue

        # 特殊コマンド
        if user_input == "/quit":
            print("終了します。")
            break
        if user_input == "/stats":
            s = get_stats()
            print(f"  [統計] ログ={s['log']} STM={s['stm']} LTM={s['ltm']}")
            continue
        if user_input == "/ltm":
            for m in load_ltm(10):
                print(f"  - {m}")
            continue

        save_log("user", user_input)

        try:
            reply = llm_chat(user_input)
        except Exception as e:
            print(f"  [ERR] LLMエラー: {e}")
            continue

        print(f"\nAI: {reply}\n")
        save_log("assistant", reply)
        run_memory_maintenance(user_input, reply)


# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────
def start_talk_ai() -> None:
    if not MODEL:
        print("エラー: .env に LITELLM_MODEL が設定されていません。")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="記憶付き日本語AIチャット")
    parser.add_argument(
        "--text", action="store_true",
        help="テキスト入力モードで起動（デフォルト: 音声モード）"
    )
    args = parser.parse_args()

    init_db()

    if args.text:
        text_loop()
    else:
        voice_loop()

