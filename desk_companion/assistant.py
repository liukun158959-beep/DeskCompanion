"""组装 Atlas Agent。配置只来自本项目 .env 和 user_state。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .envconf import require_llm_env
from .feishu_tools import AGENDA_SPEC, CREATE_EVENT_SPEC, TASKS_SPEC
from .github_tools import RECENT_SPEC, ROADMAP_SPEC, STATUS_SPEC
from .log_tools import ERROR_LOG_SPEC
from .maa_tools import bind_host, option_specs
from .skland_tools import OPERATOR_SPEC, STATUS_SPEC as SKLAND_STATUS_SPEC
from .farm_tools import PLAN_SPEC
from .facts import FORGET_SPEC, REMEMBER_SPEC, facts_prompt
from .web_search import WEB_SEARCH_SPEC
from .skill_tools import LIST_SKILLS_SPEC, READ_SKILL_SPEC
from .state import UserState

TZ = timezone(timedelta(hours=8))
EMPTY_REPLY = "模型没有给出回复。恢复：再说一次；创建日程也可以用看板的新建。"

TOOL_CONTRACT = """用户问起今天安排、日程、待办、要做什么，或消息以【今日纸条】开头时，必须先调用 get_today_agenda 和 get_open_tasks，再根据工具结果用中文 Markdown 回答：
- 先用引用块标出最该盯的一件事，第一行 **重点**，下面写事项名和截止时间
- 再用有序列表列出其余值得盯的事项
- 有多条日程或待办时再给一张表格，列用：事项、截止、状态
- 不要鸡汤，不要把所有事写成一段话
- 工具返回认证失败或 lark-cli 错误时，原样告诉用户如何修复，不要编造日程。
用户要创建日程、约时间、在日历里加一条时，必须调用 create_calendar_event，不要先调用 get_today_agenda 或 get_open_tasks。当前这句话里「现在是」那一行就是东八区的今天、明天和后天，用它把「今天」「明天」「后天」换成带时区的时间，例如 2026-10-06T09:00:00+08:00。标题和钟点都有就创建，缺了就追问，不要编钟点，也不要先问确定吗。已有同名日程也不算已经建过，仍要创建。成功后只复述工具返回的标题、开始和结束。工具失败就原样说明，不要假装已经建好。
用户要打开明日方舟、清日常、看或改日常勾选时，必须调用对应工具，不要假装游戏已开或日常已清：
- get_arknights_daily_options 查看勾选（名称与 MAA 一键长草一致）
- set_arknights_daily_options 按用户说的改勾选
- open_arknights_pc 打开鹰角启动器安装的 PC 客户端，不是安卓模拟器
- start_arknights_daily 先开游戏再按勾选准备清日常
- stop_arknights_daily 停止当前动作
用户问明日方舟理智、本周剿灭合成玉、保全额度、月卡时，必须先调用 get_arknights_skland。问某干员练到哪、精二、专精、模组时，必须先调用 get_arknights_operator，参数用游戏中文名。短名对应多名时工具会一次返回全部同名进度，按工具原文说，不要让用户再选名字，不要只复述「把名字说全」。用户问今天刷什么、刷哪、剿灭还打吗、芯片还刷吗、保全还做吗时，必须先调用 get_arknights_today_plan，只按工具原文说，不要改关卡、不要编打几次、不要因为活动开着就另推一关。不要用仓库 inventory 冒充理智和周玉，不要列出全部干员。工具说不是今天或还没同步时，告诉用户去看板「自动化任务 → 明日方舟」点对应按钮，不要编数字。用户要同步森空岛时也去看板点，对话里不要假装已经同步。
工具失败原文告诉用户怎么修。调用开游戏/清日常后立即根据工具返回说话，不要空等进度。
用户问日志、为什么挂了、仓库怎么识别错了、看看日志时，必须先调用 read_recent_errors，再调用 read_skill，技能名 maa-log-analysis，只根据这两次工具返回的原文解释。没有出错记录就说没有，不要编原因，不要根据分析去开游戏或再清日常。
用户问有哪些技能、技能库、分析日志或写飞书总结该用哪份规程时，必须先调用 list_skills。要读某份技能正文时调用 read_skill。
用户要在对话里写今日工作总结时，必须先调用 read_skill，技能名 feishu-doc-writing，只根据已有日程/待办/对话材料写，不编。用户要本周复盘、这周做了什么、周报时，告诉他打开看板「自动化任务」的「周复盘」子界面生成；不要用今日材料或 github_recent 冒充一周产出，不要假装已经写入飞书。消息里有【本轮指定】时，技能若写明正文已附在【技能正文】，按正文执行，不要再调用 read_skill；否则按列出的技能名调用 read_skill。按列出的工具名调用对应工具；指定了 GitHub 仓库时 github_recent / github_roadmap 必须用该仓库。写明飞书文档正文已附在【文档正文】时，只根据那段正文回答，不要编文档里没有的内容。写明必须调用的 mcp_ 工具时，必须调用那个工具，参数按工具要求填，失败就原样说明，不要编调用结果。
用户问 GitHub 连没连上、有哪些仓库、仓库状态或路线图总结时，必须先调用 github_status。问某仓库下一步、路线图、milestone 时必须调用 github_roadmap。要总结某仓库最近提交时，必须先调用 github_recent，再调用 read_skill，技能名 github-repo-summary，只根据工具原文在对话里说，不写飞书，不编没推送的改动。工具失败或没有 milestone issue 时原样告诉用户如何修复。
用户说出要跨对话记住的偏好、决定或长期安排时，必须调用 remember_fact。text 是一句不超过 80 字的事实。quote 必须是这一轮用户原话里的连续片段，不能是你的推断、日程、仓库数量或别的工具结果。返回里没有「已记下」就不许说已经记住。用户要忘掉某条时必须调用 forget_fact，text 必须和已有事实整句相同。返回里没有「已忘掉」就不许说已经忘掉。
用户问天气、新闻、现在、最新、网上才有的事，或【本轮指定】写了必须调用 web_search 时，必须先调用 web_search。query 用用户要查的那件事，不要改题。只根据工具返回的来源标题、摘要和链接回答，并写出用到的链接。工具失败、没有结果，或转述对不上来源，就原样说明，不要编。今日日程和【今日纸条】不要调用 web_search。
不要语音。"""


def clock_line(now: datetime) -> str:
    """东八区今天、明天、后天。只拼进发给模型的当前句，不写入对话记录。"""
    if now.tzinfo is None:
        raise RuntimeError("现在的时间必须带时区。")
    local = now.astimezone(TZ)
    tomorrow = local + timedelta(days=1)
    day_after = local + timedelta(days=2)
    return (
        f"现在是 {local.strftime('%Y-%m-%d')}，"
        f"明天是 {tomorrow.strftime('%Y-%m-%d')}，"
        f"后天是 {day_after.strftime('%Y-%m-%d')}。"
    )


def with_clock(text: str) -> str:
    """当前这句前面加日期。含【本轮指定】时日期放在标记之后，标记仍在。"""
    body = (text or "").strip()
    if not body:
        raise RuntimeError("输入框是空的。")
    line = clock_line(datetime.now(TZ))
    marker = "【本轮指定】"
    if body.startswith(marker):
        return body.replace(marker, marker + "\n" + line, 1)
    return line + "\n" + body


def spoken_answer(text: str) -> str:
    """模型没说出正文时失败，并给出恢复指引。思考不在这里。"""
    spoken = (text or "").strip()
    if not spoken:
        raise RuntimeError(EMPTY_REPLY)
    if spoken.startswith("Agent 终止："):
        raise RuntimeError("Agent 达到步骤或时间上限，请查看任务进度后继续。")
    return spoken


def build_system_prompt(persona: str) -> str:
    text = (persona or "").strip()
    if not text:
        raise RuntimeError("系统提示词为空。打开主窗「设置」填写。")
    return text + "\n\n" + facts_prompt() + "\n\n" + TOOL_CONTRACT


def _replace_system(agent, prompt: str) -> None:
    """每次开口前换成带当前事实的系统提示。clear() 会留下这条 system。"""
    rows = [
        msg
        for msg in agent.memory.runtime_messages
        if msg.get("role") == "system" and not msg.get("isMeta")
    ]
    if len(rows) != 1 or type(rows[0].get("content")) is not str:
        raise RuntimeError("模型系统提示不在，无法写入事实。恢复：重启客户端。")
    rows[0]["content"] = prompt


def inject_history(agent, rows: list[dict], *, persona: str) -> None:
    """把已经算好的历史灌进 Agent Memory。当前这句用户话由 run() 自己加。"""
    if type(persona) is not str or not persona.strip():
        raise RuntimeError("系统提示词为空。打开主窗「设置」填写。")
    if type(rows) is not list:
        raise RuntimeError("要注入的历史必须是列表。")
    _replace_system(agent, build_system_prompt(persona))
    agent.memory.clear()
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
    tools.register(**CREATE_EVENT_SPEC)
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
    tools.register(**REMEMBER_SPEC)
    tools.register(**FORGET_SPEC)
    def search(args):
        return WEB_SEARCH_SPEC["func"](
            args, on_status=lambda text: host.ui(lambda: host.on_stream_status(text)))
    tools.register(**{**WEB_SEARCH_SPEC, "func": search})
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


def react_loop_count(agent, run_id: str) -> int:
    """这一轮回答里模型被调用的次数。一次调用里的多个工具仍算 1。"""
    if type(run_id) is not str or not run_id.strip():
        raise RuntimeError("统计循环次数需要这次回答的 run_id。")
    journal = getattr(agent, "journal", None)
    get_events = getattr(journal, "get_events", None)
    if not callable(get_events):
        raise RuntimeError("这次回答没有循环记录。恢复：停掉当前客户端，在 desk-companion\\client 里重新运行 pnpm tauri dev。")
    count = 0
    for event in get_events(run_id):
        if getattr(event, "event_type", "") == "llm_after_call":
            count += 1
    if count < 1:
        raise RuntimeError("这次回答没有记到循环次数。恢复：再发一次；仍没有就重启客户端。")
    return count
