"""
test_chatgpt_parser.py — 80% 覆蓋率目標
"""
import pytest
from backend.ingest.chatgpt_parser import process, _is_learning_query, count_repeated_topics
from backend.ingest.base import SourceType


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv-001",
        "title": "遞迴學習",
        "mapping": {
            "node1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["什麼是遞迴？"]},
                    "create_time": 1000,
                }
            },
            "node2": {
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"parts": ["遞迴是函式呼叫自身的技術..."]},
                    "create_time": 1001,
                }
            },
            "node3": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["為什麼遞迴需要基底條件？"]},
                    "create_time": 1002,
                }
            },
        },
    },
    {
        "id": "conv-002",
        "title": "作業代寫",
        "mapping": {
            "node1": {
                "message": {
                    "author": {"role": "user"},
                    "content": {"parts": ["幫我寫一個排序演算法"]},
                    "create_time": 2000,
                }
            },
        },
    },
]


@pytest.mark.asyncio
async def test_process_filters_non_learning():
    chunks = await process(SAMPLE_CONVERSATIONS)
    # conv-002 應該被過濾掉
    sources = [c.source_id for c in chunks]
    assert not any("conv-002" in s for s in sources)


@pytest.mark.asyncio
async def test_process_keeps_learning_turns():
    chunks = await process(SAMPLE_CONVERSATIONS)
    assert len(chunks) >= 1
    assert all(c.is_conversation for c in chunks)
    assert all(c.source_type == SourceType.CHATGPT for c in chunks)


@pytest.mark.asyncio
async def test_process_dict_format():
    data = {"conversations": SAMPLE_CONVERSATIONS}
    chunks = await process(data)
    assert len(chunks) >= 1


def test_is_learning_query_positive():
    assert _is_learning_query("什麼是遞迴？") is True
    assert _is_learning_query("為什麼需要基底條件？") is True
    assert _is_learning_query("how does recursion work?") is True


def test_is_learning_query_negative():
    assert _is_learning_query("幫我寫一個函式") is False
    assert _is_learning_query("generate a python script") is False


@pytest.mark.asyncio
async def test_count_repeated_topics():
    chunks = await process(SAMPLE_CONVERSATIONS)
    topics = count_repeated_topics(chunks)
    # topics 是 dict，只要能正常回傳即可
    assert isinstance(topics, dict)


@pytest.mark.asyncio
async def test_invalid_format_raises():
    with pytest.raises(ValueError, match="無法識別"):
        await process({"wrong_key": []})
