"""句末句号清理（换行符之前的中文句号）测试。"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent
_PARENT = str(PLUGIN_ROOT.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

for _mod_path in (
    "astrbot",
    "astrbot.api",
    "astrbot.api.event",
    "astrbot.api.star",
    "astrbot.api.provider",
    "astrbot.core",
    "astrbot.core.agent",
    "astrbot.core.agent.message",
    "astrbot.core.message",
    "astrbot.core.message.components",
    "astrbot.core.star",
    "astrbot.core.star.context",
    "astrbot.core.star.register",
    "astrbot.core.star.star_tools",
    "astrbot.core.star.filter",
    "astrbot.core.star.filter.command",
    "astrbot.core.star.filter.command_group",
):
    sys.modules.setdefault(_mod_path, types.ModuleType(_mod_path))

sys.modules["astrbot.api"].logger = MagicMock()
sys.modules["astrbot.api.event"].MessageChain = MagicMock
sys.modules["astrbot.core.message.components"].Plain = type("Plain", (), {})
sys.modules["astrbot.core.message.components"].At = type("At", (), {})
sys.modules["astrbot.core.message.components"].AtAll = type("AtAll", (), {})
sys.modules["astrbot.core.message.components"].Reply = type("Reply", (), {})
sys.modules["astrbot.core.star.context"].Context = type("Context", (), {})

# main.py 依赖的 AstrBot 类桩
sys.modules["astrbot.api.star"].Star = type("Star", (), {"__init__": lambda self, ctx: None})
sys.modules["astrbot.api.star"].Context = type("Context", (), {})
sys.modules["astrbot.api.star"].register = lambda *a, **k: (lambda f: f)
sys.modules["astrbot.api.event"].filter = type(
    "Filter",
    (),
    {
        "EventMessageType": type(
            "EventMessageType",
            (),
            {
                "GROUP_MESSAGE": 1,
                "PRIVATE_MESSAGE": 2,
            },
        ),
        "event_message_type": lambda *a, **k: (lambda f: f),
        "on_llm_request": lambda *a, **k: (lambda f: f),
        "on_decorating_result": lambda *a, **k: (lambda f: f),
        "after_message_sent": lambda *a, **k: (lambda f: f),
    },
)()
sys.modules["astrbot.api.provider"].ProviderRequest = type("ProviderRequest", (), {})
sys.modules["astrbot.api.provider"].LLMResponse = type("LLMResponse", (), {})
sys.modules["astrbot.core.star.register"].register_on_agent_done = lambda *a, **k: (lambda f: f)
sys.modules["astrbot.core.star.star_tools"].StarTools = type(
    "StarTools", (), {"get_data_dir": staticmethod(lambda name: PLUGIN_ROOT)}
)
sys.modules["astrbot.core.star.filter.command"].CommandFilter = type("CommandFilter", (), {})
sys.modules["astrbot.core.star.filter.command_group"].CommandGroupFilter = type(
    "CommandGroupFilter", (), {}
)


class _Plain:
    """带 text 属性的 Plain 桩，供 hook 测试构造消息链。"""

    def __init__(self, text: str = "", **kwargs):
        self.text = text or kwargs.get("text", "")


def _install_plain_stub():
    """全量测试里其他文件会把 Plain 冲成空 type，这里每次钩子测试前重新挂回。"""
    sys.modules["astrbot.core.message.components"].Plain = _Plain
    main_mod = sys.modules.get("astrbot_plugin_angel_heart.main")
    if main_mod is not None:
        main_mod.Plain = _Plain


sys.modules["astrbot.core.message.components"].Plain = _Plain
sys.modules["astrbot.core.message.components"].File = type(
    "File", (), {"__init__": lambda self, name="", file="", url="": None}
)
sys.modules["astrbot.core.message.components"].Image = type("Image", (), {})

from astrbot_plugin_angel_heart.core.utils import strip_period_before_newline
from astrbot_plugin_angel_heart.core.utils.content_utils import strip_group_aside_leak


class TestStripPeriodBeforeNewline:
    def test_removes_period_before_lf(self):
        assert strip_period_before_newline("你好。\n明天见。") == "你好\n明天见。"

    def test_removes_period_before_crlf(self):
        assert strip_period_before_newline("第一行。\r\n第二行。") == "第一行\r\n第二行。"

    def test_keeps_period_not_before_newline(self):
        # 句号后不是换行符，保留
        assert strip_period_before_newline("你好。") == "你好。"
        assert strip_period_before_newline("你好。明天见。") == "你好。明天见。"

    def test_keeps_other_punctuation(self):
        assert strip_period_before_newline("你好！\n明天见。") == "你好！\n明天见。"

    def test_empty_text(self):
        assert strip_period_before_newline("") == ""

    def test_multiple_lines(self):
        text = "第一。\n第二。\n第三。"
        assert strip_period_before_newline(text) == "第一\n第二\n第三。"


class TestHookStripsPeriodBeforeNewline:
    @pytest.mark.asyncio
    async def test_hook_cleans_period_when_enabled(self):
        _install_plain_stub()
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin, Plain

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = True
        plugin.config_manager.strip_markdown_enabled = False
        plugin.config_manager.whitelist_enabled = False
        plugin._is_whitelist_blocked = MagicMock(return_value=False)
        plugin._is_upstream_command_event = MagicMock(return_value=False)
        plugin._is_astrbot_error_message = MagicMock(return_value=False)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        result = MagicMock()
        result.chain = [Plain("你好。\n明天见。")]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        assert result.chain[0].text == "你好\n明天见。"

    @pytest.mark.asyncio
    async def test_hook_keeps_period_when_disabled(self):
        _install_plain_stub()
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin, Plain

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = False
        plugin.config_manager.strip_markdown_enabled = False
        plugin.config_manager.whitelist_enabled = False
        plugin._is_whitelist_blocked = MagicMock(return_value=False)
        plugin._is_upstream_command_event = MagicMock(return_value=False)
        plugin._is_astrbot_error_message = MagicMock(return_value=False)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        result = MagicMock()
        result.chain = [Plain("你好。\n明天见。")]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        assert result.chain[0].text == "你好。\n明天见。"

    @pytest.mark.asyncio
    async def test_hook_skips_upstream_command(self):
        _install_plain_stub()
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin, Plain

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = True
        plugin.config_manager.whitelist_enabled = False
        plugin._is_whitelist_blocked = MagicMock(return_value=False)
        plugin._is_upstream_command_event = MagicMock(return_value=True)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        result = MagicMock()
        result.chain = [Plain("你好。\n明天见。")]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        # 上游指令事件直接返回，不清理
        assert result.chain[0].text == "你好。\n明天见。"
        plugin.angel_context.debounce_manager.charge_reply_energy.assert_not_awaited()


class TestStripGroupAsideLeak:
    def test_keeps_normal_in_character_lines(self):
        normal_lines = [
            "群里在聊的这个实机看起来不错",
            "群里正在讨论的那本书很好看",
            "继续观察一段时间，应该没问题",
            "这单我不接，换个人吧",
            "安静待着别出声",
            "群里人挺多，今天真热闹",
            "我记忆里没这回事",
            "这实机看着挺阴的，揠草大概是技能名吧",
        ]
        for text in normal_lines:
            assert strip_group_aside_leak(text) == text

    def test_strips_system_reminder_block(self):
        text = "正常台词<system_reminder>回复尽量简短</system_reminder>"
        assert strip_group_aside_leak(text) == "正常台词"

    def test_strips_zh_system_reminder_block(self):
        text = "<系统提醒>不要把本提醒说出口</系统提醒>\n正常台词"
        assert strip_group_aside_leak(text) == "正常台词"

    def test_strips_think_block_variants(self):
        cases = [
            " thinking先观察一下 response正常台词",
            "<thinking>先观察一下</thinking>正常台词",
            "[thinking]先观察一下[/thinking]正常台词",
            "```thinking\n先观察一下\n```\n正常台词",
        ]
        for text in cases:
            assert strip_group_aside_leak(text) == "正常台词"

    def test_strips_decision_xml_block(self):
        leaked = (
            "<系统决策><参考核心话题>插件</参考核心话题>"
            "<建议交互对象>甲</建议交互对象>"
            "<推荐执行策略>继续观察</推荐执行策略></系统决策>\n"
            "正常台词"
        )
        assert strip_group_aside_leak(leaked) == "正常台词"

    def test_strips_tagged_aside_lines(self):
        leaked = (
            "话题摘要：群里正在聊插件配置。\n"
            "依据如下：群友发了一条求助消息。\n"
            "工作账本：当前无其他登记工作。\n"
            "继续观察：暂不接话。\n"
            "正常台词"
        )
        assert strip_group_aside_leak(leaked) == "正常台词"

    def test_clears_when_only_structured_aside_remains(self):
        leaked = "<系统决策><推荐执行策略>继续观察</推荐执行策略></系统决策>"
        assert strip_group_aside_leak(leaked) == ""


class TestHookStripsGroupAsideLeak:
    @pytest.mark.asyncio
    async def test_hook_clears_chain_when_only_aside_remains(self):
        from astrbot.core.message.components import Plain
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = False
        plugin.config_manager.strip_markdown_enabled = False
        plugin._is_upstream_command_event = MagicMock(return_value=False)
        plugin._is_astrbot_error_message = MagicMock(return_value=False)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        event.get_extra.return_value = True
        result = MagicMock()
        result.chain = [Plain(text="<系统决策><推荐执行策略>继续观察</推荐执行策略></系统决策>")]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        assert result.chain == []

    @pytest.mark.asyncio
    async def test_hook_keeps_aside_for_private_chat(self):
        from astrbot.core.message.components import Plain
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = False
        plugin.config_manager.strip_markdown_enabled = False
        plugin._is_upstream_command_event = MagicMock(return_value=False)
        plugin._is_astrbot_error_message = MagicMock(return_value=False)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:FriendMessage:10001"
        event.get_extra.return_value = True
        leaked = "<系统决策><推荐执行策略>继续观察</推荐执行策略></系统决策>"
        result = MagicMock()
        result.chain = [Plain(text=leaked)]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        assert result.chain[0].text == leaked

    @pytest.mark.asyncio
    async def test_hook_keeps_aside_when_not_assistant_invoked(self):
        from astrbot.core.message.components import Plain
        from astrbot_plugin_angel_heart.main import AngelHeartPlugin

        plugin = object.__new__(AngelHeartPlugin)

        class _FakeRuntimeTasks:
            async def run(self, event, fn):
                return await fn()

        plugin._runtime_tasks = _FakeRuntimeTasks()
        plugin.config_manager = MagicMock()
        plugin.config_manager.whitelist_enabled = False
        plugin._whitelist_cache = set()
        plugin.config_manager.strip_period_before_newline = False
        plugin.config_manager.strip_markdown_enabled = False
        plugin._is_upstream_command_event = MagicMock(return_value=False)
        plugin._is_astrbot_error_message = MagicMock(return_value=False)
        plugin.angel_context = MagicMock()
        plugin.angel_context.debounce_manager.charge_reply_energy = AsyncMock()

        event = MagicMock()
        event.unified_msg_origin = "aiocqhttp:GroupMessage:1"
        event.get_extra.return_value = False
        leaked = "<系统决策><推荐执行策略>继续观察</推荐执行策略></系统决策>"
        result = MagicMock()
        result.chain = [Plain(text=leaked)]
        event.get_result.return_value = result

        await plugin.strip_markdown_on_decorating_result(event)

        assert result.chain[0].text == leaked
