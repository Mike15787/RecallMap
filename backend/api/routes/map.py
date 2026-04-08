"""
GET  /v1/sessions/{id}/map   — 取得學習地圖（首次呼叫觸發盲點偵測）
POST /v1/sessions/{id}/turns — 送出蘇格拉底對話輪次
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.engine import learning_map as lm_module
from backend.api.store import session_store

router = APIRouter()


@router.get("/{session_id}/map")
async def get_learning_map(session_id: str, force: bool = False):
    """
    分析目前 session 的 chunks，產生學習地圖。
    force=true 時強制重新分析（忽略快取）。
    """
    sess = await session_store.get_or_404(session_id)

    if not sess["chunks"]:
        raise HTTPException(status_code=422, detail="尚未上傳任何學習材料")

    # 若已有地圖且未強制刷新，直接回傳
    if sess["learning_map"] and not force:
        return sess["learning_map"]

    # 偵測盲點 → 建學習地圖
    from backend.engine import blind_spot as bs_module
    spots = await bs_module.detect(sess["chunks"])
    sess["blind_spots"] = spots

    learning_map = lm_module.LearningMap(session_id=session_id)
    learning_map.add_blind_spots(spots)
    sess["learning_map"] = learning_map.to_dict()

    await session_store.save(sess)
    return sess["learning_map"]


class TurnRequest(BaseModel):
    blind_spot_id: str
    user_message: str


@router.post("/{session_id}/turns")
async def post_turn(session_id: str, body: TurnRequest):
    """送出一輪蘇格拉底對話"""
    sess = await session_store.get_or_404(session_id)

    # 找到對應盲點
    spot = next((s for s in sess["blind_spots"] if s.blind_spot_id == body.blind_spot_id), None)
    if not spot:
        raise HTTPException(status_code=404, detail=f"找不到盲點：{body.blind_spot_id}")

    from backend.engine import dialogue as dlg

    # 取出或建立對話 session
    dial_sess = sess["dialogue_sessions"].get(body.blind_spot_id)
    if not dial_sess:
        # 第一輪：由 AI 開場
        opening = await dlg.start_dialogue(concept=spot.concept)
        dial_sess = dlg.DialogueSession(
            session_id=f"dlg-{uuid.uuid4().hex[:8]}",
            blind_spot_id=body.blind_spot_id,
            concept=spot.concept,
        )
        dial_sess.turns.append(dlg.DialogueTurn(role="assistant", content=opening))
        sess["dialogue_sessions"][body.blind_spot_id] = dial_sess
        await session_store.save(sess)
        return {"role": "assistant", "content": opening, "depth": None, "is_completed": False}

    # 後續輪次
    dial_sess.turns.append(dlg.DialogueTurn(role="user", content=body.user_message))
    ai_response, depth = await dlg.continue_dialogue(
        concept=spot.concept,
        history=dial_sess.turns,
        user_answer=body.user_message,
    )
    dial_sess.turns.append(dlg.DialogueTurn(role="assistant", content=ai_response))

    if depth >= 0.8:
        dial_sess.is_completed = True
        dial_sess.final_confidence = depth
        # 更新學習地圖
        now = datetime.now(tz=timezone.utc).isoformat()
        if sess["learning_map"]:
            lmap = lm_module.LearningMap(session_id=session_id)
            lmap.nodes = [
                lm_module.MapNode(**{k: v for k, v in n.items() if k != "zone"}, zone=lm_module.ZoneType(n["zone"]))
                for n in sess["learning_map"]["nodes"]
            ]
            lmap.update_node(body.blind_spot_id, depth, now)
            sess["learning_map"] = lmap.to_dict()

    await session_store.save(sess)
    return {
        "role": "assistant",
        "content": ai_response,
        "depth": round(depth, 2),
        "is_completed": dial_sess.is_completed,
    }
