from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
_PARENT = str(PLUGIN_ROOT.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

for _mod_path in (
    "astrbot",
    "astrbot.api",
    "astrbot.api.event",
    "astrbot.core",
    "astrbot.core.agent",
    "astrbot.core.agent.message",
    "astrbot.core.message",
    "astrbot.core.message.components",
    "astrbot.core.star",
    "astrbot.core.star.context",
):
    sys.modules.setdefault(_mod_path, types.ModuleType(_mod_path))

sys.modules["astrbot.api"].logger = MagicMock()
sys.modules["astrbot.core.message.components"].Image = type("Image", (), {})
sys.modules["astrbot.core.message.components"].At = type("At", (), {})
sys.modules["astrbot.core.message.components"].File = type("File", (), {})
sys.modules["astrbot.core.star.context"].Context = type("Context", (), {})
sys.modules["astrbot.core.agent.message"].ImageURLPart = type(
    "ImageURLPart",
    (),
    {"__init__": lambda self, image_url: setattr(self, "image_url", SimpleNamespace(**image_url))},
)
sys.modules["astrbot.core.agent.message"].TextPart = type(
    "TextPart",
    (),
    {"__init__": lambda self, text: setattr(self, "text", text)},
)

from astrbot_plugin_angel_heart.roles.front_desk import FrontDesk
from astrbot_plugin_angel_heart.core.work_ledger import WorkLedger


def _front_desk():
    config = MagicMock()
    config.for_chat.return_value = config
    config.alias = "fairy"
    config.image_caption_provider_id = ""
    config.focus_instructions = "分析 总结 好好想想 为什么 到底"
    config.normal_reply_max_chars = 20
    config.focus_reply_max_chars = 200
    angel = MagicMock()
    angel.work_ledger = WorkLedger()
    angel.astr_context = MagicMock()
    fd = FrontDesk(config, angel)
    fd._provider_supports_images = MagicMock(return_value=False)
    fd.filter_images_for_provider = MagicMock(side_effect=lambda _chat_id, contexts: contexts)
    return fd, angel


def _event(message_id: str):
    class E:
        unified_msg_origin = "aiocqhttp:GroupMessage:10000"
        message_str = ""
        message_obj = SimpleNamespace(message_id=message_id)

        def __init__(self):
            self._extras = {}

        def get_extra(self, key, default=None):
            return self._extras.get(key, default)

        def set_extra(self, key, value):
            self._extras[key] = value

    return E()


async def _run_group_rewrite(fd, event, req, recent_dialogue, historical_context):
    event.set_extra(
        "angelheart_decision_context",
        {
            "recent_dialogue": recent_dialogue,
            "historical_context": historical_context,
            "boundary_ts": 3.0,
        },
    )
    await fd.rewrite_prompt_for_llm("aiocqhttp:GroupMessage:10000", event, req)


def test_split_recent_dialogue_uses_message_id_boundary():
    fd, _ = _front_desk()
    before, current = fd._split_recent_dialogue_at_current_message(
        [
            {"source_message_id": "m1", "content": "第一条"},
            {"source_message_id": "m2", "content": "第二条"},
            {"source_message_id": "m3", "content": "第三条"},
        ],
        "m3",
    )

    assert [m["source_message_id"] for m in before] == ["m1", "m2"]
    assert [m["source_message_id"] for m in current] == ["m3"]


def test_work_ledger_context_does_not_repeat_current_work_text():
    fd, angel = _front_desk()
    angel.work_ledger.start_work(
        chat_id="aiocqhttp:GroupMessage:10000",
        work_id="current",
        trigger_message_id="m3",
        trigger_summary="第三条当前消息",
    )
    angel.work_ledger.start_work(
        chat_id="aiocqhttp:GroupMessage:10000",
        work_id="other",
        trigger_message_id="m1",
        trigger_summary="别的工作",
    )

    class E:
        def get_extra(self, key, default=None):
            if key == "angelheart_work_id":
                return "current"
            return default

    text = fd._build_temporary_work_ledger_reminder("aiocqhttp:GroupMessage:10000", E())

    assert text is not None
    assert "第三条当前消息" not in text
    assert "别的工作" in text


def test_group_rewrite_keeps_assistant_history_in_contexts_and_only_current_message_in_prompt():
    import asyncio

    fd, angel = _front_desk()
    angel.work_ledger.start_work(
        chat_id="aiocqhttp:GroupMessage:10000",
        work_id="current",
        trigger_message_id="m3",
        trigger_summary="第三条当前消息",
    )
    angel.work_ledger.start_work(
        chat_id="aiocqhttp:GroupMessage:10000",
        work_id="other",
        trigger_message_id="m0",
        trigger_summary="已有其他工作",
    )

    req = SimpleNamespace(
        contexts=[],
        prompt="",
        image_urls=[],
        extra_user_content_parts=[],
        system_prompt="BASE SYSTEM",
    )
    event = _event("m3")
    event.set_extra("angelheart_work_id", "current")

    recent_dialogue = [
        {
            "role": "user",
            "content": "第一条用户",
            "sender_name": "甲",
            "sender_id": "1001",
            "timestamp": 1.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m1",
        },
        {
            "role": "assistant",
            "content": "第二条助理",
            "sender_name": "assistant",
            "sender_id": "bot",
            "timestamp": 2.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m2",
        },
        {
            "role": "user",
            "content": "第三条当前消息",
            "sender_name": "丙",
            "sender_id": "1003",
            "timestamp": 3.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m3",
        },
    ]

    asyncio.run(_run_group_rewrite(fd, event, req, recent_dialogue, historical_context=[]))

    assert "第三条当前消息" in req.prompt
    assert "第一条用户" not in req.prompt
    assert "第二条助理" not in req.prompt

    context_texts = []
    for message in req.contexts:
        content = message.get("content", "")
        if isinstance(content, str):
            context_texts.append(content)
        elif isinstance(content, list):
            context_texts.append("".join(item.get("text", "") for item in content if isinstance(item, dict)))

    joined_context = "\n".join(context_texts)
    assert "第一条用户" in joined_context
    assert "第二条助理" in joined_context
    assert "第三条当前消息" not in joined_context
    assert any(message.get("role") == "assistant" for message in req.contexts)
    # 内部提醒进 system_prompt，不再出现在用户上下文或 extra_user_content_parts。
    assert all(
        message.get("sender_id") not in ("angelheart-work-ledger", "angelheart-reply-length")
        for message in req.contexts
    )
    assert "这是一个群聊场景。" not in joined_context
    extra_texts = "".join(
        getattr(part, "text", "") for part in req.extra_user_content_parts
    )
    assert "<system_reminder>" not in extra_texts
    assert "已有其他工作" not in extra_texts
    assert "回复尽量简短" not in extra_texts
    assert req.system_prompt.startswith("BASE SYSTEM")
    assert "你正在一个群聊中扮演角色，你的昵称是 'fairy'。" in req.system_prompt
    assert "可以直接发进群里的角色台词" in req.system_prompt
    assert "禁止输出旁白、话题摘要、内部判断、记忆有无" in req.system_prompt
    assert "禁止把系统提醒说出口" in req.system_prompt
    assert "你输出的每一个字都会作为群消息发出" in req.system_prompt
    assert "<system_reminder>" in req.system_prompt
    assert "已有其他工作" in req.system_prompt
    assert "回复尽量简短，通常一两句话、20 字左右即可说清。" in req.system_prompt
    assert "不要正反面讲解，直接给出你认为的最佳结论，不需要推理过程。" in req.system_prompt
    assert "不要把本提醒说出口。" in req.system_prompt


def test_group_rewrite_adds_boundary_placeholder_when_history_starts_with_assistant():
    import asyncio

    fd, _ = _front_desk()
    req = SimpleNamespace(
        contexts=[],
        prompt="",
        image_urls=[],
        extra_user_content_parts=[],
        system_prompt="BASE SYSTEM",
    )
    event = _event("m2")
    recent_dialogue = [
        {
            "role": "assistant",
            "content": "上一条是助理发言",
            "sender_name": "assistant",
            "sender_id": "bot",
            "timestamp": 1.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m1",
        },
        {
            "role": "user",
            "content": "第二条当前消息",
            "sender_name": "甲",
            "sender_id": "1001",
            "timestamp": 2.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m2",
        },
    ]

    asyncio.run(_run_group_rewrite(fd, event, req, recent_dialogue, historical_context=[]))

    assert req.contexts[0]["role"] == "user"
    assert "（历史记录）" in req.contexts[0]["content"][0]["text"]
    assert "这是一个群聊场景。" not in req.prompt


def test_group_rewrite_uses_focus_reply_length_when_focus_instruction_hits():
    import asyncio

    fd, _ = _front_desk()
    req = SimpleNamespace(
        contexts=[],
        prompt="",
        image_urls=[],
        extra_user_content_parts=[],
        system_prompt="BASE SYSTEM",
    )
    event = _event("m3")
    recent_dialogue = [
        {
            "role": "user",
            "content": "帮我好好想想这个问题",
            "sender_name": "甲",
            "sender_id": "1001",
            "timestamp": 3.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m3",
            "metadata": {
                "body_text": "帮我好好想想这个问题",
                "hits": [{"type": "focus", "phrase": "好好想想"}],
            },
        }
    ]

    asyncio.run(_run_group_rewrite(fd, event, req, recent_dialogue, historical_context=[]))

    extra_texts = "".join(
        getattr(part, "text", "") for part in req.extra_user_content_parts
    )
    assert "请认真回答" not in extra_texts
    assert "请认真回答：先给结论，再给必要依据，长度以 200 字左右为宜。" in req.system_prompt
    assert "如果是分析的，不要正反面讲解，直接给出你认为的最佳结论，只给出必要的关键推理。" in req.system_prompt
    assert "不要把本提醒说出口。" in req.system_prompt


def test_private_rewrite_does_not_inject_reply_length_reminder():
    import asyncio

    fd, _ = _front_desk()
    chat_id = "aiocqhttp:FriendMessage:10000"
    req = SimpleNamespace(
        contexts=[],
        prompt="",
        image_urls=[],
        extra_user_content_parts=[],
        system_prompt="BASE SYSTEM",
    )
    event = _event("m1")
    event.unified_msg_origin = chat_id
    fd._get_decision_context_for_rewrite = MagicMock(
        return_value=(
            [
                {
                    "role": "user",
                    "content": "帮我好好想想这个问题",
                    "sender_name": "甲",
                    "sender_id": "1001",
                    "timestamp": 1.0,
                    "chat_id": chat_id,
                    "source_message_id": "m1",
                }
            ],
            [],
            1.0,
        )
    )
    fd._ensure_minimum_context = AsyncMock()

    async def _run():
        await fd.rewrite_prompt_for_llm(chat_id, event, req)

    asyncio.run(_run())

    assert all(
        message.get("sender_id") != "angelheart-reply-length" for message in req.contexts
    )
    assert "回复尽量简短" not in req.prompt
    assert "长度以" not in req.prompt


def test_group_rewrite_replaces_current_astrbot_image_attachment_path_with_ledger_cache_path():
    import asyncio

    fd, _ = _front_desk()
    req = SimpleNamespace(
        contexts=[],
        prompt="",
        image_urls=["/AstrBot/data/temp/compressed_wrong.jpg"],
        extra_user_content_parts=[
            SimpleNamespace(text="[Image Attachment: path /AstrBot/data/temp/compressed_wrong.jpg]"),
            SimpleNamespace(text="[Image Attachment in quoted message: path /AstrBot/data/temp/quoted.jpg]"),
        ],
        system_prompt="BASE SYSTEM",
    )
    event = _event("m-current")
    cache_path = r"E:\github\ai-qq\astrbot\data\plugin_data\astrbot_plugin_angel_heart\media_cache\chat\image.webp"

    recent_dialogue = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这是真的假的"},
                {
                    "type": "image_url",
                    "image_url": {"url": cache_path},
                    "cache_path": cache_path,
                    "local_file_path": cache_path,
                    "original_url": cache_path,
                    "original_file_url": cache_path,
                },
            ],
            "sender_name": "红豆泥",
            "sender_id": "289104862",
            "timestamp": 3.0,
            "chat_id": "aiocqhttp:GroupMessage:10000",
            "source_message_id": "m-current",
        },
    ]

    asyncio.run(_run_group_rewrite(fd, event, req, recent_dialogue, historical_context=[]))

    assert req.image_urls == []
    assert req.extra_user_content_parts[0].text == f"[Image Attachment: path {cache_path}]"
    assert req.extra_user_content_parts[1].text == "[Image Attachment in quoted message: path /AstrBot/data/temp/quoted.jpg]"
    assert cache_path not in req.prompt
    assert "[图片1]" in req.prompt
