"""
SM-2 間隔複習排程模組
RUNTIME: edge（純演算法，不需要模型）
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


# ── SM-2 演算法 ──────────────────────────────────────────────────────────────

@dataclass
class SM2Card:
    concept: str
    blind_spot_id: str
    ease_factor: float = 2.5    # 難易度因子，初始 2.5
    interval: int = 1           # 下次複習間隔（天）
    repetition: int = 0         # 已複習次數
    next_review: datetime | None = None

    def review(self, quality: int) -> None:
        """
        更新 SM-2 參數。
        quality: 0–5（0=完全忘記, 5=完全記得）
        """
        if quality >= 3:
            if self.repetition == 0:
                self.interval = 1
            elif self.repetition == 1:
                self.interval = 6
            else:
                self.interval = round(self.interval * self.ease_factor)
            self.repetition += 1
        else:
            self.repetition = 0
            self.interval = 1

        self.ease_factor = max(
            1.3,
            self.ease_factor + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02),
        )
        self.next_review = datetime.now(tz=timezone.utc) + timedelta(days=self.interval)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "blind_spot_id": self.blind_spot_id,
            "ease_factor": round(self.ease_factor, 2),
            "interval": self.interval,
            "repetition": self.repetition,
            "next_review": self.next_review.isoformat() if self.next_review else None,
        }


# ── 排程建議器 ───────────────────────────────────────────────────────────────

@dataclass
class ReviewEvent:
    concept: str
    blind_spot_id: str
    suggested_start: datetime
    duration_minutes: int = 20
    round_number: int = 1           # 第幾輪複習


def build_review_schedule(
    blind_spots: list,              # list[BlindSpot]
    exam_date: datetime | None,
    free_slots: list[dict] | None = None,
) -> list[ReviewEvent]:
    """
    根據盲點列表和考試日期，建立 SM-2 複習排程。
    free_slots 格式：[{"start": datetime, "end": datetime}, ...]
    """
    if not blind_spots:
        return []

    now = datetime.now(tz=timezone.utc)
    events: list[ReviewEvent] = []
    cards = [SM2Card(concept=bs.concept, blind_spot_id=bs.blind_spot_id) for bs in blind_spots]

    # 按信心度排序：信心越低，越早複習
    cards.sort(key=lambda c: next(
        (bs.confidence for bs in blind_spots if bs.blind_spot_id == c.blind_spot_id), 0.5
    ))

    # 最多安排到考試日（或 30 天後）
    deadline = exam_date or (now + timedelta(days=30))

    current = now + timedelta(hours=1)
    for card in cards:
        # 第一輪：立即
        slot_start = _find_slot(current, 20, free_slots)
        if slot_start and slot_start < deadline:
            events.append(
                ReviewEvent(
                    concept=card.concept,
                    blind_spot_id=card.blind_spot_id,
                    suggested_start=slot_start,
                    duration_minutes=20,
                    round_number=1,
                )
            )
            card.review(quality=3)  # 預設第一輪品質中等
            current = slot_start + timedelta(minutes=30)

        # 第二輪：按 SM-2 間隔
        if card.next_review and card.next_review < deadline:
            slot2 = _find_slot(card.next_review, 15, free_slots)
            if slot2:
                events.append(
                    ReviewEvent(
                        concept=card.concept,
                        blind_spot_id=card.blind_spot_id,
                        suggested_start=slot2,
                        duration_minutes=15,
                        round_number=2,
                    )
                )

    events.sort(key=lambda e: e.suggested_start)
    return events


def _find_slot(
    preferred: datetime,
    duration_minutes: int,
    free_slots: list[dict] | None,
) -> datetime | None:
    """從空檔列表中找到最接近 preferred 的可用時段"""
    if not free_slots:
        # 沒有空檔資料，直接用建議時間
        return preferred

    for slot in free_slots:
        start = slot["start"]
        end = slot["end"]
        if start >= preferred and (end - start).total_seconds() >= duration_minutes * 60:
            return start

    return preferred  # fallback
