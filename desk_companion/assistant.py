"""组装 Atlas Agent。配置只来自本项目 .env 和 user_state。"""
from __future__ import annotations

from .envconf import require_llm_env
from .feishu_tools import AGENDA_SPEC, TASKS_SPEC
from .github_tools import RECENT_SPEC, ROADMAP_SPEC, STATUS_SPEC
from .log_tools import ERROR_LOG_SPEC
from .maa_tools import bind_host, option_specs
from .skland_tools import OPERATOR_SPEC, STATUS_SPEC as SKLAND_STATUS_SPEC
from .farm_tools import PLAN_SPEC
from .skill_tools import LIST_SKILLS_SPEC, READ_SKILL_SPEC
from .memory import history_for_model
from .state import UserState

TOOL_CONTRACT = """用户问起今天安排、日程、待办、要做什么，或消息以【今日纸条】开头时，必须先调用 get_today_agenda 和 get_open_tasks，再根据工具结果用中文 Markdown 回答：
- 先用引用块标出最该盯的一件事，第一行 **重点**，下面写事项名和截止时间
- 再用有序列表列出其余值得盯的事项
- 有多条日程或待办时再给一张表格，列用：事项、截止、状态
- 不要鸡汤，不要把所有事写成一段话
- 工具返回认证失败或 lark-cli 错误时，原样告诉用户如何修复，不要编造日程。
用户要打开明日方舟、清日常、看或改日常勾选时，必须调用对应工具，不要假装游戏已开或日常已清：
- get_arknights_daily_options 查看勾选（名称与 MAA 一键长草一致）
- set_arknights_daily_options 按用户说的改勾选
- open_arknights_pc 打开鹰角启动器安装的 PC 客户端，不是安卓模拟器
- start_arknights_daily 先开游戏再按勾选准备清日常
- stop_arknights_daily 停止当前动作
用户问明日方舟理智、本周剿灭合成玉、保全额度、月卡时，必须先调用 get_arknights_skland。问某干员练到哪、精二、专精、模组时，必须先调用 get_arknights_operator，参数用游戏中文名。短名对应多名时工具会一次返回全部同名进度，按工具原文说，不要让用户再选名字，不要只复述「把名字说全」。用户问今天刷什么、刷哪、剿灭还打吗、芯片还刷吗、保全还做吗时，必须先调用 get_arknights_today_plan，只按工具原文说，不要改关卡、不要编打几次、不要因为活动开着就另推一关。不要用仓库 inventory 冒充理智和周玉，不要列出全部干员。工具说不是今天或还没同步时，告诉用户去看板「明日方舟」点对应按钮，不要编数字。用户要同步森空岛时也去看板点，对话里不要假装已经同步。
工具失败原文告诉用户怎么修。调用开游戏/清日常后立即根据工具返回说话，不要空等进度。
用户问日志、为什么挂了、仓库怎么识别错了、看看日志时，必须先调用 read_recent_errors，再调用 read_skill，技能名 maa-log-analysis，只根据这两次工具返回的原文解释。没有出错记录就说没有，不要编原因，不要根据分析去开游戏或再清日常。
用户问有哪些技能、技能库、分析日志或写飞书总结该用哪份规程时，必须先调用 list_skills。要读某份技能正文时调用 read_skill。
用户要在对话里写今日工作总结时，必须先调用 read_skill，技能名 feishu-doc-writing，只根据已有日程/待办/对话材料写，不编。用户要本周复盘、这周做了什么、周报时，告诉他去看板点「生成本周复盘」，不要用今日材料或 github_recent 冒充一周产出。
用户问 GitHub 连没连上、有哪些仓库、仓库状态或路线图总结时，必须先调用 github_status。问某仓库下一步、路线图、milestone 时必须调用 github_roadmap。要总结某仓库最近提交时，必须先调用 github_recent，再调用 read_skill，技能名 github-repo-summary，只根据工具原文在对话里说，不写飞书，不编没推送的改动。工具失败或没有 milestone issue 时原样告诉用户如何修复。
不要语音。"""


def build_system_prompt(persona: str) -> str:
    text = (persona or "").strip()
    if not text:
        raise RuntimeError("人设为空。打开看板「人设」页填写。")
    return text + "\n\n" + TOOL_CONTRACT


def inject_history(agent, history_n: int, *, exclude_user: str | None = None) -> None:
    """把 jsonl 去重后的最近 N 条灌进 Agent Memory。当前这句用户话由 run() 自己加。"""
    agent.memory.clear()
    if history_n <= 0:
        return
    extra = 1 if exclude_user else 0
    rows = history_for_model(history_n + extra)
    if (
        exclude_user
        and rows
        and rows[-1].get("role") == "user"
        and rows[-1].get("text") == exclude_user
    ):
        rows = rows[:-1]
    rows = rows[-history_n:]
    for rec in rows:
        role = rec["role"]
        text = rec["text"]
        if role == "user":
            agent.memory.add_user(text)
        elif role == "pet":
            agent.memory.add_assistant({"role": "assistant", "content": text})
        else:
            raise RuntimeError(f"对话记录角色无法注入模型：{role!r}。")


def list_providers() -> list[dict]:
    try:
        from atlas.providers import PROVIDERS
    except ImportError as exc:
        raise RuntimeError(
            "未安装 Atlas，无法列出模型提供商。请 pip install -e <Atlas目录>。"
        ) from exc
    out = []
    for key, info in PROVIDERS.items():
        out.append(
            {
                "id": key,
                "name": info["name"],
                "base_url": info["base_url"],
                "default_model": info["default_model"],
            }
        )
    return out


def token_plugin(agent):
    for plugin in agent.plugin_manager.plugins:
        if plugin.name == "token_cost":
            return plugin
    raise RuntimeError("Agent 未注册 TokenCostPlugin，无法统计 token。")


def build_agent(host):
    try:
        from atlas import Agent, LLM, Toolkit
        from atlas.journal import InMemoryJournal
        from atlas.plugins.token_cost import TokenCostPlugin
    except ImportError as exc:
        raise RuntimeError(
            "未安装 Atlas。本项目不在 Atlas 仓库内。请在本机执行: "
            "pip install -e <Atlas目录>"
        ) from exc

    if host is None:
        raise RuntimeError("build_agent 需要 host，才能挂气泡流式和用量。")
    state: UserState = host.state
    cfg = require_llm_env()
    bind_host(host)
    tools = Toolkit()
    tools.register(**AGENDA_SPEC)
    tools.register(**TASKS_SPEC)
    tools.register(**STATUS_SPEC)
    tools.register(**ROADMAP_SPEC)
    tools.register(**RECENT_SPEC)
    tools.register(**ERROR_LOG_SPEC)
    tools.register(**LIST_SKILLS_SPEC)
    tools.register(**READ_SKILL_SPEC)
    for spec in option_specs():
        tools.register(**spec)
    tools.register(**SKLAND_STATUS_SPEC)
    tools.register(**OPERATOR_SPEC)
    tools.register(**PLAN_SPEC)
    agent = Agent(
        llm=LLM(
            api_key=cfg["ATLAS_API_KEY"],
            base_url=cfg["ATLAS_BASE_URL"],
            model=cfg["ATLAS_MODEL"],
        ),
        tools=tools,
        system_prompt=build_system_prompt(state.persona),
        journal=InMemoryJournal(save_full_payload=True),
        max_steps=state.max_steps,
    )
    from .stream_plugin import BubbleStreamPlugin

    agent.plugin_manager.register(BubbleStreamPlugin(host=host))
    agent.plugin_manager.register(TokenCostPlugin(log_summary=False))
    return agent
