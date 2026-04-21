import sqlite3
from datetime import datetime, timedelta

DB_NAME = "data/memory.db"

# =====================
# 初期化
# =====================
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    # 短期記憶
    cur.execute("""
    CREATE TABLE IF NOT EXISTS short_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        role TEXT NOT NULL,        -- user / assistant
        content TEXT NOT NULL,
        created_at TEXT NOT NULL,
        access_count INTEGER DEFAULT 0
    )
    """)

    # 長期記憶
    cur.execute("""
    CREATE TABLE IF NOT EXISTS long_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        importance REAL NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()

# =====================
# 短期記憶
# =====================
def add_short_memory(role: str, text: str):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO short_memory (role, content, created_at, access_count)
        VALUES (?, ?, ?, 0)
    """, (role, text, datetime.now().isoformat()))

    conn.commit()
    conn.close()

def reinforce_short_memory():
    """参照された短期記憶を強化"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        UPDATE short_memory
        SET access_count = access_count + 1
    """)

    conn.commit()
    conn.close()

def cleanup_short_memory(max_items=30):
    """古い短期記憶を削除"""
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT id FROM short_memory
        ORDER BY created_at DESC
        LIMIT -1 OFFSET ?
    """, (max_items,))

    for (mem_id,) in cur.fetchall():
        cur.execute("DELETE FROM short_memory WHERE id = ?", (mem_id,))

    conn.commit()
    conn.close()

# =====================
# STM → LTM
# =====================
def consolidate_memory(min_access=3, max_age_minutes=5):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, role, content, access_count, created_at
        FROM short_memory
    """)
    rows = cur.fetchall()

    now = datetime.now()

    for mem_id, role, content, access, created_at in rows:
        age = now - datetime.fromisoformat(created_at)

        # ✅ user発言のみ長期記憶候補
        if role != "user":
            continue

        if access >= min_access or age >= timedelta(minutes=max_age_minutes):
            importance = min(1.0, access / 10)

            cur.execute("""
                INSERT INTO long_memory (content, importance, created_at)
                VALUES (?, ?, ?)
            """, (content, importance, now.isoformat()))

            cur.execute("DELETE FROM short_memory WHERE id = ?", (mem_id,))

    conn.commit()
    conn.close()

# =====================
# 長期記憶の減衰
# =====================
def decay_long_memory(decay_rate=0.02, threshold=0.2):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT id, importance, created_at
        FROM long_memory
    """)
    rows = cur.fetchall()

    now = datetime.now()

    for mem_id, importance, created_at in rows:
        days = (now - datetime.fromisoformat(created_at)).days
        new_importance = importance - decay_rate * days

        if new_importance <= threshold:
            cur.execute("DELETE FROM long_memory WHERE id = ?", (mem_id,))
        else:
            cur.execute("""
                UPDATE long_memory
                SET importance = ?
                WHERE id = ?
            """, (new_importance, mem_id))

    conn.commit()
    conn.close()

# =====================
# 長期記憶読み込み
# =====================
def load_long_memories(limit=5):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        SELECT content
        FROM long_memory
        ORDER BY importance DESC, created_at DESC
        LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]