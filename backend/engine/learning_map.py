"""
學習地圖資料結構與管理
RUNTIME: edge（純邏輯，不需要模型）
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import uuid


class ZoneType(Enum):
    KNOWN   = "known"   # 已知區
    FUZZY   = "fuzzy"   # 模糊區
    BLIND   = "blind"   # 盲點區


@dataclass
class MapNode:
    node_id: str
    concept: str
    zone: ZoneType
    confidence: float           # 0.0–1.0
    evidence: list[str] = field(default_factory=list)
    repeat_count: int = 0
    last_reviewed: str | None = None  # ISO 8601


@dataclass
class LearningMap:
    session_id: str
    nodes: list[MapNode] = field(default_factory=list)

    def add_blind_spots(self, blind_spots: list) -> None:
        """從 BlindSpot 列表新增盲點節點"""
        for spot in blind_spots:
            node_id = f"bs-{uuid.uuid4().hex[:8]}"
            zone = _confidence_to_zone(spot.confidence)
            self.nodes.append(
                MapNode(
                    node_id=node_id,
                    concept=spot.concept,
                    zone=zone,
                    confidence=spot.confidence,
                    evidence=spot.evidence,
                    repeat_count=spot.repeat_count,
                )
            )
            # 回填 blind_spot_id
            spot.blind_spot_id = node_id

    def update_node(self, node_id: str, new_confidence: float, reviewed_at: str) -> None:
        """蘇格拉底對話結束後更新理解程度"""
        for node in self.nodes:
            if node.node_id == node_id:
                node.confidence = new_confidence
                node.zone = _confidence_to_zone(new_confidence)
                node.last_reviewed = reviewed_at
                break

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "summary": {
                "known": sum(1 for n in self.nodes if n.zone == ZoneType.KNOWN),
                "fuzzy": sum(1 for n in self.nodes if n.zone == ZoneType.FUZZY),
                "blind": sum(1 for n in self.nodes if n.zone == ZoneType.BLIND),
            },
            "nodes": [
                {
                    "node_id": n.node_id,
                    "concept": n.concept,
                    "zone": n.zone.value,
                    "confidence": n.confidence,
                    "evidence": n.evidence,
                    "repeat_count": n.repeat_count,
                    "last_reviewed": n.last_reviewed,
                }
                for n in self.nodes
            ],
        }


def _confidence_to_zone(confidence: float) -> ZoneType:
    if confidence >= 0.75:
        return ZoneType.KNOWN
    elif confidence >= 0.45:
        return ZoneType.FUZZY
    else:
        return ZoneType.BLIND
