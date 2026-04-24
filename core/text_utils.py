import re


# ─────────────────────────────────────────────
# LLM 出力クリーニング
# ─────────────────────────────────────────────

def strip_think_tags(text: str) -> str:
    """DeepSeek-R1 などの <think>...</think> ブロックを除去する"""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def strip_action_brackets(text: str) -> str:
    """
    括弧で囲まれた行動・感情描写を中身ごと除去する。

    対象:
        （全角丸括弧）  →  除去
        (半角丸括弧)    →  除去
        「鉤括弧」      →  除去
        *アスタリスク*  →  除去
        [角括弧]        →  除去
    """
    text = re.sub(r'（[^（）]*）', '', text)   # 全角（）
    text = re.sub(r'\([^()]*\)',   '', text)   # 半角()
    text = re.sub(r'「[^「」]*」', '', text)   # 鉤括弧「」
    text = re.sub(r'\*[^*]+\*',   '', text)   # *アスタリスク*
    text = re.sub(r'\[[^\[\]]*\]', '', text)  # 角括弧[]
    text = re.sub(r' +',           ' ', text)  # 連続スペース整理
    return text.strip()


def clean_reply(text: str) -> str:
    """
    LLM の返答に対して全クリーニングを適用する。
    talk_ai.py の llm_chat と speak_ai.py の speak の両方から呼ぶ共通関数。

    処理順:
        1. <think> タグ除去
        2. 括弧アクション除去
    """
    text = strip_think_tags(text)
    text = strip_action_brackets(text)
    return text
