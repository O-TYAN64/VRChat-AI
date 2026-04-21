import os
import sqlite3
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import MeCab

# ─────────────────────────────────────────────
# 設定
# ─────────────────────────────────────────────
DB_PATH = Path("data/memory.db")

# MeCabの辞書パス（.env で上書き可能）
# 例: MECAB_IPADIC=C:/Program Files/MeCab/dic/ipadic
MECAB_IPADIC  = os.getenv("MECAB_IPADIC",  r"C:\MeCab\dic\ipadic")
MECAB_NEOLOGD = os.getenv("MECAB_NEOLOGD", r"C:\MeCab\dic\NEologd\NEologd.20200910-u.dic")

STM_MAX_WORD_LEN   = int(os.getenv("STM_MAX_WORD_LEN", "2"))      # STMに入れる最小文字数
STM_SENTENCE_MAX   = int(os.getenv("STM_SENTENCE_MAX", "30"))      # STM文の最大長
STM_EXPIRE_MIN     = int(os.getenv("STM_EXPIRE_MIN", "30"))      # STM忘却タイムアウト（分）
STM_TO_LTM_WEIGHT  = int(os.getenv("STM_TO_LTM_WEIGHT", "3"))       # LTMに昇格する閾値
LTM_DECAY_RATE     = float(os.getenv("LTM_DECAY_RATE", "0.02"))    # LTM減衰率（/日）
LTM_DECAY_LIMIT    = float(os.getenv("LTM_DECAY_LIMIT", "0.2"))     # この信頼度以下で削除
LTM_LOAD_LIMIT     = int(os.getenv("LTM_LOAD_LIMIT", "5"))       # 取得するLTM件数

# ─────────────────────────────────────────────
# ログ設定
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 不要語リスト
# ─────────────────────────────────────────────
STOP_WORDS: set[str] = {
    "する", "いる", "ある", "なる", "やる", "できる",
    "思う", "言う", "話す", "見る", "聞く",
    "行く", "来る", "入る", "出る", "帰る",
    "しまう", "おく", "みる", "続ける", "始める", "終わる",
    "感じる", "考える", "分かる", "知る",
    "ある程度", "ちょっと",
}

# ─────────────────────────────────────────────
# MeCab 初期化（遅延シングルトン）
# ─────────────────────────────────────────────
_tagger: Optional[MeCab.Tagger] = None


def _find_dicrc(base: str) -> Optional[str]:
    """dicrc ファイルを探して辞書ディレクトリを返す。見つからなければ None"""
    candidates = [
        base,
        base.replace("/", "\\"),
        base.replace("\\", "/"),
    ]
    for c in candidates:
        dicrc = os.path.join(c, "dicrc")
        if os.path.exists(dicrc):
            return c
    return None


def _get_tagger() -> MeCab.Tagger:
    global _tagger
    if _tagger is None:
        # dicrc の存在確認
        ipadic_real = _find_dicrc(MECAB_IPADIC)
        if ipadic_real is None:
            raise FileNotFoundError(
                f"MeCab ipadic 辞書が見つかりません: {MECAB_IPADIC}\n"
                f"  .env の MECAB_IPADIC に dicrc があるディレクトリを指定してください。\n"
                f"  例: MECAB_IPADIC=C:/MeCab/dic/ipadic"
            )

        # スラッシュに統一（MeCab はバックスラッシュをエスケープ文字として解釈する）
        ipadic_path = ipadic_real.replace("\\", "/")
        args = f"-d {ipadic_path}"

        if MECAB_NEOLOGD and os.path.exists(MECAB_NEOLOGD):
            neologd_path = MECAB_NEOLOGD.replace("\\", "/")
            args += f" -u {neologd_path}"
        elif MECAB_NEOLOGD:
            logger.warning(f"NEologd 辞書が見つかりません（スキップ）: {MECAB_NEOLOGD}")

        logger.info(f"MeCab 初期化 args: {args}")
        try:
            _tagger = MeCab.Tagger(args)
            logger.info("MeCab 初期化完了")
        except Exception as e:
            logger.error(f"MeCab 初期化失敗: {e}")
            raise
    return _tagger


# ─────────────────────────────────────────────
# DB ユーティリティ
# ─────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """DB初期化（テーブル作成）"""
    with _get_conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversation_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            role       TEXT    NOT NULL CHECK(role IN ('user', 'assistant')),
            content    TEXT    NOT NULL,
            created_at TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stm (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            kind      TEXT    NOT NULL CHECK(kind IN ('word', 'sentence')),
            content   TEXT    NOT NULL,
            weight    REAL    NOT NULL DEFAULT 1.0,
            last_seen TEXT    NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_stm ON stm(kind, content);

        CREATE TABLE IF NOT EXISTS ltm (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            content    TEXT    NOT NULL UNIQUE,
            confidence REAL    NOT NULL DEFAULT 0.0,
            updated_at TEXT    NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_stm_last_seen ON stm(last_seen);
        CREATE INDEX IF NOT EXISTS idx_ltm_confidence ON ltm(confidence DESC);
        """)
    logger.info("DB初期化完了")


# ─────────────────────────────────────────────
# 会話ログ
# ─────────────────────────────────────────────
def save_log(role: str, text: str) -> None:
    """会話ログを保存する"""
    if role not in ("user", "assistant"):
        raise ValueError(f"role は 'user' か 'assistant' のみ: {role!r}")
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_log (role, content, created_at) VALUES (?, ?, ?)",
            (role, text, datetime.now().isoformat()),
        )
    logger.debug(f"[log] role={role} content={text[:30]!r}")


def load_recent_log(limit: int = 20) -> list[dict]:
    """直近の会話ログを取得する"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, created_at FROM conversation_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


# ─────────────────────────────────────────────
# テキスト加工
# ─────────────────────────────────────────────
def make_short_sentence(text: str, max_len: int = STM_SENTENCE_MAX) -> str:
    """記憶用に文を短縮する"""
    ENDINGS = ["なんだよね", "だよ", "です", "でした", "かな", "と思う", "ですよ", "だね"]
    short = text
    for e in ENDINGS:
        if short.endswith(e):
            short = short[: -len(e)]
            break
    short = short.strip("。！？　 ")
    return short[:max_len]


def extract_stm_units(text: str) -> list[tuple[str, str]]:
    """
    テキストから (kind, content) のリストを抽出する。
    kind: 'word' | 'sentence'
    """
    tagger = _get_tagger()
    units: list[tuple[str, str]] = []

    node = tagger.parseToNode(text)
    while node:
        surface = node.surface
        features = node.feature.split(",")
        part    = features[0]
        subpart = features[1] if len(features) > 1 else ""
        base    = features[6] if len(features) > 6 and features[6] != "*" else surface

        # 名詞（数・代名詞・非自立 は除外）
        if part == "名詞" and subpart not in ("数", "代名詞", "非自立"):
            if len(base) >= STM_MAX_WORD_LEN:
                units.append(("word", base))

        # 動詞（非自立・ストップワード 除外）
        elif part == "動詞":
            if subpart != "非自立" and base not in STOP_WORDS:
                if len(base) >= STM_MAX_WORD_LEN:
                    units.append(("word", base))

        # 形容詞
        elif part == "形容詞":
            if len(base) >= STM_MAX_WORD_LEN:
                units.append(("word", base))

        node = node.next

    # 文全体も短縮して記憶
    short = make_short_sentence(text)
    if len(short) >= 5:
        units.append(("sentence", short))

    return units


# ─────────────────────────────────────────────
# STM 操作
# ─────────────────────────────────────────────
def add_stm(kind: str, content: str) -> None:
    """STMに追加または重みを増やす"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO stm (kind, content, weight, last_seen)
            VALUES (?, ?, 1.0, ?)
            ON CONFLICT(kind, content)
            DO UPDATE SET weight = weight + 1, last_seen = excluded.last_seen
            """,
            (kind, content, now),
        )
    logger.debug(f"[STM] {kind}: {content!r}")


def process_text_to_stm(text: str) -> None:
    """テキストを解析してSTMに一括登録する。MeCab が使えない場合はスキップ"""
    try:
        units = extract_stm_units(text)
    except (FileNotFoundError, RuntimeError) as e:
        logger.warning(f"[STM] MeCab 使用不可のためスキップ: {e}")
        return
    for kind, content in units:
        add_stm(kind, content)


def cleanup_stm(minutes: int = STM_EXPIRE_MIN) -> int:
    """期限切れのSTMを削除する。削除件数を返す"""
    threshold = (datetime.now() - timedelta(minutes=minutes)).isoformat()
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM stm WHERE last_seen < ?", (threshold,))
        deleted = cur.rowcount
    if deleted:
        logger.info(f"[STM] 忘却: {deleted} 件")
    return deleted


def load_stm(limit: int = 20) -> list[dict]:
    """現在のSTMを取得する（重み降順）"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT kind, content, weight FROM stm ORDER BY weight DESC, last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────
# LTM 操作
# ─────────────────────────────────────────────
def consolidate(min_weight: int = STM_TO_LTM_WEIGHT) -> int:
    """STMの安定した文をLTMに昇格する。昇格件数を返す"""
    now = datetime.now().isoformat()
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT id, content, weight FROM stm WHERE kind = 'sentence' AND weight >= ?",
            (min_weight,),
        ).fetchall()

        count = 0
        for row in rows:
            stm_id, content, weight = row["id"], row["content"], row["weight"]
            confidence = min(1.0, weight / 5)
            conn.execute(
                """
                INSERT INTO ltm (content, confidence, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(content)
                DO UPDATE SET confidence = MIN(1.0, confidence + 0.2), updated_at = excluded.updated_at
                """,
                (content, confidence, now),
            )
            conn.execute("DELETE FROM stm WHERE id = ?", (stm_id,))
            count += 1

    if count:
        logger.info(f"[LTM] 昇格: {count} 件")
    return count


def decay_ltm(rate: float = LTM_DECAY_RATE, limit: float = LTM_DECAY_LIMIT) -> int:
    """LTMを時間経過で減衰・削除する。削除件数を返す"""
    with _get_conn() as conn:
        rows = conn.execute("SELECT id, confidence, updated_at FROM ltm").fetchall()
        now = datetime.now()
        deleted = 0

        for row in rows:
            mem_id, conf, updated = row["id"], row["confidence"], row["updated_at"]
            try:
                days = (now - datetime.fromisoformat(updated)).days
            except ValueError:
                days = 0
            new_conf = conf - rate * days

            if new_conf <= limit:
                conn.execute("DELETE FROM ltm WHERE id = ?", (mem_id,))
                deleted += 1
            else:
                conn.execute("UPDATE ltm SET confidence = ? WHERE id = ?", (new_conf, mem_id))

    if deleted:
        logger.info(f"[LTM] 減衰削除: {deleted} 件")
    return deleted


def load_ltm(limit: int = LTM_LOAD_LIMIT) -> list[str]:
    """LTMを信頼度降順で取得する"""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT content FROM ltm ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r["content"] for r in rows]


# ─────────────────────────────────────────────
# 統計情報
# ─────────────────────────────────────────────
def get_stats() -> dict:
    """DB内の件数統計を返す"""
    with _get_conn() as conn:
        log_count = conn.execute("SELECT COUNT(*) FROM conversation_log").fetchone()[0]
        stm_count = conn.execute("SELECT COUNT(*) FROM stm").fetchone()[0]
        ltm_count = conn.execute("SELECT COUNT(*) FROM ltm").fetchone()[0]
    return {"log": log_count, "stm": stm_count, "ltm": ltm_count}