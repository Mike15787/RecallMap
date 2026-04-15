"""
Session 觸發器 — 掃描所有概念狀態，依優先順序組裝下次學習 session
RUNTIME: edge（純邏輯，不呼叫 AI）

優先順序：盲點修復 > 到期記憶複習 > 理解深化
連續多天未開 App → 到期越久優先級越高
每次 session 上限 10–15 個概念
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.engine import knowledge_base as kb
from backend.db.connection import get_db

logger = logging.getLogger(__name__)

SESSION_MAX_CONCEPTS = 15


# ── 資料類別 ──────────────────────────────────────────────────────────────────

@dataclass
class SessionItem:
    concept_id: str
    concept_name: str
    topic_id: str
    priority: str           # "blind_spot" / "retention_due" / "comprehension"
    comprehension_score: float
    retention_score: float
    next_review_due: datetime | None
    pending_confirmation: bool


@dataclass
class SessionPlan:
    items: list[SessionItem] = field(default_factory=list)
    has_pending_confirmations: bool = False
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ── 公開介面 ──────────────────────────────────────────────────────────────────

async def build_session(max_items: int = SESSION_MAX_CONCEPTS) -> SessionPlan:
    """
    掃描全部 active 概念，依優先順序回傳下次建議的學習 session。
    """
    now = datetime.now(timezone.utc)

    async with get_db() as db:
        async with db.execute(
            """SELECT * FROM mastery_records
               WHERE intent = 'active'
               ORDER BY updated_at DESC""",
        ) as cur:
            rows = [dict(r) for r in await cur.fetchall()]

    blind_spots: list[SessionItem] = []
    retention_due: list[SessionItem] = []
    comprehension: list[SessionItem] = []
    pending_confirmations = False

    for row in rows:
        item = SessionItem(
            concept_id=row["concept_id"],
            concept_name=row["concept_name"],
            topic_id=row["topic_id"],
            priority="comprehension",
            comprehension_score=row["comprehension_score"],
            retention_score=row["retention_score"],
            next_review_due=_parse_dt(row["next_review_due"]),
            pending_confirmation=bool(row["pending_confirmation"]),
        )

        if bool(row["pending_confirmation"]):
            pending_confirmations = True

        # 分類
        if row["comprehension_score"] < 0.4:
            item.priority = "blind_spot"
            blind_spots.append(item)
        elif _is_retention_due(row["next_review_due"], now):
            item.priority = "retention_due"
            # 到期越久 → 排越前（依 next_review_due 正序）
            retention_due.append(item)
        else:
            item.priority = "comprehension"
            comprehension.append(item)

    # 依優先級排序
    retention_due.sort(key=lambda x: x.next_review_due or now)
    blind_spots.sort(key=lambda x: x.comprehension_score)  # 分數越低越優先
    comprehension.sort(key=lambda x: -x.comprehension_score)  # 分數越高優先深化

    selected: list[SessionItem] = []
    for pool in (blind_spots, retention_due, comprehension):
        remaining = max_items - len(selected)
        if remaining <= 0:
            break
        selected.extend(pool[:remaining])

    return SessionPlan(
        items=selected[:max_items],
        has_pending_confirmations=pending_confirmations,
        generated_at=now,
    )


# ── 內部函式 ──────────────────────────────────────────────────────────────────

def _parse_dt(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val)


def _is_retention_due(next_review_due: str | None, now: datetime) -> bool:
    if not next_review_due:
        return True  # 從未複習過 → 視為到期
    due = datetime.fromisoformat(next_review_due)
    if due.tzinfo is None:
        from datetime import timezone as tz
        due = due.replace(tzinfo=tz.utc)
    return due <= now
