"""
SQLite 資料表定義
所有 CREATE TABLE 語句集中於此，db/connection.py 的 init_db() 會依序執行。
"""

CREATE_TABLES: list[str] = [
    # ── 主題知識庫 ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS topics (
        topic_id    TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        language    TEXT NOT NULL DEFAULT 'zh-TW',
        created_at  TEXT NOT NULL
    )
    """,

    # ── 主題 chunks（chunks 歸屬到主題，跨 session 保留）─────────────────────
    """
    CREATE TABLE IF NOT EXISTS topic_chunks (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        topic_id        TEXT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
        content         TEXT NOT NULL,
        source_type     TEXT NOT NULL,
        source_id       TEXT NOT NULL,
        metadata        TEXT NOT NULL DEFAULT '{}',
        is_conversation INTEGER NOT NULL DEFAULT 0,
        language        TEXT NOT NULL DEFAULT 'zh-TW'
    )
    """,

    # ── 概念掌握度（雙軸：理解軸 + 記憶軸）──────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS mastery_records (
        concept_id              TEXT PRIMARY KEY,
        topic_id                TEXT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
        concept_name            TEXT NOT NULL,
        -- 理解軸
        comprehension_score     REAL    NOT NULL DEFAULT 0.0,
        comprehension_level     TEXT    NOT NULL DEFAULT 'none',
        last_comprehension_test TEXT,
        pending_confirmation    INTEGER NOT NULL DEFAULT 0,
        pending_since           TEXT,
        -- 記憶軸
        retention_score         REAL    NOT NULL DEFAULT 0.0,
        sm2_interval            INTEGER NOT NULL DEFAULT 1,
        sm2_repetitions         INTEGER NOT NULL DEFAULT 0,
        sm2_ease_factor         REAL    NOT NULL DEFAULT 2.5,
        last_retention_test     TEXT,
        next_review_due         TEXT,
        -- 使用者意圖
        intent                  TEXT    NOT NULL DEFAULT 'active',
        snooze_until            TEXT,
        created_at              TEXT    NOT NULL,
        updated_at              TEXT    NOT NULL
    )
    """,

    # ── 理解軸事件紀錄 ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS comprehension_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        concept_id      TEXT    NOT NULL REFERENCES mastery_records(concept_id) ON DELETE CASCADE,
        timestamp       TEXT    NOT NULL,
        question_type   TEXT    NOT NULL,
        user_answer     TEXT    NOT NULL,
        gemma_verdict   TEXT    NOT NULL,
        gemma_reasoning TEXT    NOT NULL DEFAULT '',
        score_delta     REAL    NOT NULL DEFAULT 0.0,
        is_delayed_test INTEGER NOT NULL DEFAULT 0
    )
    """,

    # ── 記憶軸事件紀錄（SM-2）────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS retention_events (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        concept_id       TEXT    NOT NULL REFERENCES mastery_records(concept_id) ON DELETE CASCADE,
        timestamp        TEXT    NOT NULL,
        question_type    TEXT    NOT NULL,
        response_quality INTEGER NOT NULL,
        new_interval     INTEGER NOT NULL,
        new_easiness     REAL    NOT NULL
    )
    """,
]
