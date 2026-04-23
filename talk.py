import os
import sys
import threading
import argparse
from dotenv import load_dotenv
from litellm import completion
from memory_system import (
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
# 設定（.env）
# ─────────────────────────────────────────────
MODEL    = os.getenv("LITELLM_MODEL")
PROVIDER = os.getenv("LITELLM_PROVIDER")
TIMEOUT  = float(os.getenv("LLM_TIMEOUT", 60))
MAX_HISTORY        = int(os.getenv("MAX_HISTORY", 40))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", 2048))
LTM_TOP = 5
WAKE_WORD_ENABLED = os.getenv("WAKE_WORD_ENABLED", "False").lower() == "true"
WAKE_WORDS = [w.strip() for w in os.getenv("WAKE_WORD", "えーあい,AI,あい").split(",")]
PERSONA_TEXT = ""
PERSONA_FILE = os.getenv("PERSONA_FILE")
if PERSONA_FILE and os.path.exists(PERSONA_FILE):
    with open(PERSONA_FILE, "r", encoding="utf-8") as f:
        PERSONA_TEXT = f.read()
# ─────────────────────────────────────────────
# トークン簡易推定
# ─────────────────────────────────────────────
def estimate_tokens(text: str) -> int:
    # 日本語会話用の割り切り推定
    return len(text)
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
- () や 「」 を使って行動や感情の表現をしない
- 一度に話す量は1〜2文
- 無理に質問しない
# NG行動
- 箇条書き
- 教師口調
- 尋問のような質問
- 機械的な返答
"""
# ─────────────────────────────────────────────
# コンテキスト制限付き messages 構築
# ─────────────────────────────────────────────
def build_messages_with_limit(user_text: str, system_text: str) -> list:
    history = load_recent_log(MAX_HISTORY)
    messages = []
    total_tokens = estimate_tokens(system_text)
    # 履歴を後ろから積む
    for h in reversed(history):
        role = "user" if h["role"] == "user" else "assistant"
        content = h["content"]
        t = estimate_tokens(content)
        if total_tokens + t > MAX_CONTEXT_TOKENS:
            break
        messages.insert(0, {"role": role, "content": content})
        total_tokens += t
    # 最後の user 入力
    ut = estimate_tokens(user_text)
    if total_tokens + ut <= MAX_CONTEXT_TOKENS:
        messages.append({"role": "user", "content": user_text})
    else:
        messages.append(
            {"role": "user", "content": user_text[-MAX_CONTEXT_TOKENS:]}
        )
    return messages
# ─────────────────────────────────────────────
# LLM 呼び出し
# ─────────────────────────────────────────────
def llm_chat(text: str) -> str:
    system_prompt = build_system_prompt()
    messages = build_messages_with_limit(text, system_prompt)
    res = completion(
        model=MODEL,
        custom_llm_provider=PROVIDER,
        messages=[
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        timeout=TIMEOUT,
    )
    return res["choices"][0]["message"]["content"]
# ─────────────────────────────────────────────
# 記憶メンテナンス
# ─────────────────────────────────────────────
def run_memory_maintenance(user_text: str, ai_text: str) -> None:
    process_text_to_stm(user_text)
    process_text_to_stm(ai_text)
    consolidate()
    cleanup_stm()
    decay_ltm()
# ─────────────────────────────────────────────
# ウェイクワード制御
# ─────────────────────────────────────────────
def handle_wake_control(text: str) -> str | None:
    global WAKE_WORD_ENABLED
    if "呼びかけオフ" in text:
        WAKE_WORD_ENABLED = False
        return "呼びかけをオフにしました。"
    if "呼びかけオン" in text:
        WAKE_WORD_ENABLED = True
        return "呼びかけをオンにしました。"
    return None
def extract_wake_text(text: str) -> tuple[bool, str]:
    if not WAKE_WORD_ENABLED:
        return True, text.strip()
    for w in WAKE_WORDS:
        if w in text:
            return True, text.replace(w, "", 1).strip(" 、。！？")
    return False, ""
# ─────────────────────────────────────────────
# 音声モード
# ─────────────────────────────────────────────
def _speak_async(text: str) -> None:
    from speak_ai import speak
    threading.Thread(target=speak, args=(text,), daemon=True).start()
def voice_loop() -> None:
    from mic_input import transcribe_audio
    print("🎧 音声AIモード 起動")
    print(f"モデル: {MODEL} / プロバイダ: {PROVIDER}")
    print(f"コンテキスト上限: {MAX_CONTEXT_TOKENS}")
    print(f"ウェイクワード: {'有効' if WAKE_WORD_ENABLED else '無効'} / ワード: {WAKE_WORDS}")
    print("-"*40)
    while True:
        user_text = transcribe_audio()
        memory_stats = get_stats()
        print(f"[MEMORY] STM: {memory_stats['stm']} / LTM: {memory_stats['ltm']}")
        if not user_text:
            continue
        print(f"[USER] {user_text}")
        control = handle_wake_control(user_text)
        if control:
            _speak_async(control)
            continue
        is_woke, clean_text = extract_wake_text(user_text)
        if not is_woke or not clean_text:
            continue
        save_log("user", clean_text)
        try:
            reply = llm_chat(clean_text)
        except Exception as e:
            print(f"[ERR] {e}")
            continue
        print(f"[AI] {reply}")
        save_log("assistant", reply)
        _speak_async(reply)
        run_memory_maintenance(clean_text, reply)
# ─────────────────────────────────────────────
# テキストモード
# ─────────────────────────────────────────────
def text_loop() -> None:
    print("テキストモード（/quit で終了）")
    print(f"モデル: {MODEL} / 上限: {MAX_CONTEXT_TOKENS}")
    print()
    while True:
        try:
            user_input = input("あなた: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input:
            continue
        if user_input == "/quit":
            break
        save_log("user", user_input)
        try:
            reply = llm_chat(user_input)
        except Exception as e:
            print(f"[ERR] {e}")
            continue
        print(f"\nAI: {reply}\n")
        save_log("assistant", reply)
        run_memory_maintenance(user_input, reply)
# ─────────────────────────────────────────────
# エントリーポイント
# ─────────────────────────────────────────────
def start_talk_ai() -> None:
    if not MODEL:
        print("エラー: LITELLM_MODEL 未設定")
        sys.exit(1)
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", action="store_true")
    args = parser.parse_args()
    init_db()
    if args.text:
        text_loop()
    else:
        voice_loop()
if __name__ == "__main__":
    start_talk_ai()