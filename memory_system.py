import sqlite3
from datetime import datetime, timedelta
import MeCab

DB_PATH = "data/memory.db"

# =====================
# ※ MeCab 初期化
# ・Windows + ipadic + NEologd の例
# ・環境に合わせてパス調整OK
# =====================
tagger = MeCab.Tagger(
    r'-d "C:\\Program Files\\MeCab\\dic\\ipadic" '
    r'-u "C:\\Program Files\\MeCab\\dic\\NEologd\\NEologd.20200910-u.dic"'
)

# =====================
# ※ DB初期化
# ・会話ログ / STM / LTM の3テーブルを作る
# =====================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ※ 会話ログ（発言をそのまま保存）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS conversation_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT,
        content TEXT,
        created_at TEXT
    )
    """)

    # ※ STM（短期記憶：単語・短文）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stm (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT,          -- word / sentence
        content TEXT,
        weight REAL,
        last_seen TEXT
    )
    """)

    # ※ LTM（長期記憶：安定した短文）
    cur.execute("""
    CREATE TABLE IF NOT EXISTS ltm (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT UNIQUE,
        confidence REAL,
        updated_at TEXT
    )
    """)

    conn.commit()
    conn.close()


# =====================
# ※ 会話ログ保存
# ・ユーザー / AI の発言を加工せず保存
# =====================
def save_log(role: str, text: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO conversation_log (role, content, created_at)
        VALUES (?, ?, ?)
    """, (role, text, datetime.now().isoformat()))

    conn.commit()
    conn.close()


# =====================
# ※ 短い文章を作る
# ・記憶用に30文字以内にする
# =====================
def make_short_sentence(text: str, max_len=30):
    ENDINGS = ["なんだよね", "だよ", "です", "でした", "かな", "と思う"]

    short = text
    for e in ENDINGS:
        if short.endswith(e):
            short = short.replace(e, "")

    short = short.strip("。！？ ")

    if len(short) > max_len:
        short = short[:max_len]

    return short


# =====================
# ※ STM抽出（MeCab＋不要語フィルタ）
# ・名詞 / 重要な動詞 / 形容詞のみ
# ・短い文章も同時に追加
# =====================
def extract_stm(text: str):
    units = []

    STOP_WORDS = {
        "する", "いる", "ある", "なる",
        "思う", "言う", "見る", "聞く",
        "できる", "やる", "行く", "来る",
    }

    node = tagger.parseToNode(text)
    while node:
        features = node.feature.split(",")
        part = features[0]
        subpart = features[1]
        base = features[6] if len(features) > 6 else node.surface

        # 名詞
        if part == "名詞" and subpart not in ["数", "代名詞", "非自立"]:
            if len(base) >= 2:
                units.append(("word", base))

        # 動詞
        elif part == "動詞":
            if subpart != "非自立" and base not in STOP_WORDS:
                if len(base) >= 2:
                    units.append(("word", base))

        # 形容詞
        elif part == "形容詞":
            if len(base) >= 2:
                units.append(("word", base))

        node = node.next

    # ※ 短い文章としても覚える
    short_sentence = make_short_sentence(text)
    if len(short_sentence) >= 5:
        units.append(("sentence", short_sentence))

    return units


# =====================
# ※ STM保存・強化
# ・同じ内容なら重みを増やす
# =====================
def add_stm(kind: str, content: str):
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT id FROM stm
        WHERE kind = ? AND content = ?
    """, (kind, content))

    row = cur.fetchone()

    if row:
        cur.execute("""
            UPDATE stm
            SET weight = weight + 1,
                last_seen = ?
            WHERE id = ?
        """, (now, row[0]))
    else:
        cur.execute("""
            INSERT INTO stm (kind, content, weight, last_seen)
            VALUES (?, ?, 1.0, ?)
        """, (kind, content, now))

    conn.commit()
    conn.close()


# =====================
# ※ STM → LTM
# ・よく出る短文だけ長期記憶へ
# =====================
def consolidate(min_weight=3):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat()

    cur.execute("""
        SELECT id, content, weight FROM stm
        WHERE kind = 'sentence' AND weight >= ?
    """, (min_weight,))

    rows = cur.fetchall()

    for stm_id, content, weight in rows:
        confidence = min(1.0, weight / 5)

        cur.execute("""
            INSERT INTO ltm (content, confidence, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(content)
            DO UPDATE SET
                confidence = confidence + 0.2,
                updated_at = ?
        """, (content, confidence, now, now))

        cur.execute("DELETE FROM stm WHERE id = ?", (stm_id,))

    conn.commit()
    conn.close()


# =====================
# ※ STM忘却
# =====================
def cleanup_stm(minutes=30):
    threshold = (datetime.now() - timedelta(minutes=minutes)).isoformat()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM stm
        WHERE last_seen < ?
    """, (threshold,))

    conn.commit()
    conn.close()


# =====================
# ※ LTM減衰
# =====================
def decay_ltm(rate=0.02, limit=0.2):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, confidence, updated_at FROM ltm")
    rows = cur.fetchall()
    now = datetime.now()

    for mem_id, conf, updated in rows:
        days = (now - datetime.fromisoformat(updated)).days
        new_conf = conf - rate * days

        if new_conf <= limit:
            cur.execute("DELETE FROM ltm WHERE id = ?", (mem_id,))
        else:
            cur.execute("""
                UPDATE ltm
                SET confidence = ?
                WHERE id = ?
            """, (new_conf, mem_id))

    conn.commit()
    conn.close()


# =====================
# ※ LTM読み込み
# =====================
def load_ltm(limit=5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT content FROM ltm
        ORDER BY confidence DESC, updated_at DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    return [r[0] for r in rows]