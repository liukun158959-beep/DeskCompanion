"""看板对话工作台：session、输入点选、复盘写入飞书。"""
from __future__ import annotations

import json
import os

from .memory import list_chat, list_sessions
from .state import new_session_id

CLI_CHIPS = (
    ("get_today_agenda", "今日日程"),
    ("get_open_tasks", "未完成待办"),
    ("github_status", "GitHub 状态"),
    ("github_recent", "GitHub 近况"),
    ("github_roadmap", "GitHub 路线图"),
)
MAA_CHIPS = (
    ("open_game", "打开游戏"),
    ("start_daily", "开始清日常"),
    ("stop", "停止清日常"),
    ("sync_skland", "同步森空岛"),
    ("today_farm", "今天刷什么"),
)
NEED_REPO_TOOLS = frozenset({"github_recent", "github_roadmap"})


class BoardWorkbench:
    def board_composer_options(self) -> dict:
        from .skill_catalog import list_skills

        try:
            skills = [
                {"id": item["id"], "label": item["id"], "description": item["description"]}
                for item in list_skills()
            ]
        except Exception as extra:
            return {"ok": False, "error": str(extra)}
        github = {"ok": True, "items": []}
        try:
            from .github import list_owned_repos

            github = {
                "ok": True,
                "items": [
                    {"id": row["full_name"], "label": row["full_name"]}
                    for row in list_owned_repos()
                ],
            }
        except Exception as extra:
            github = {"ok": False, "error": str(extra), "items": []}
        return {
            "ok": True,
            "skills": skills,
            "cli": [{"id": key, "label": label} for key, label in CLI_CHIPS],
            "github": github,
            "maa": [{"id": key, "label": label} for key, label in MAA_CHIPS],
        }

    def new_chat_session(self) -> dict:
        try:
            if self._agent_running:
                raise RuntimeError("凯尔希正在说话，等这句说完再开新对话。")
            current = list_chat(self.state.session_id)
            if current:
                self.state.session_id = new_session_id()
                self.state.save()
            self._reload_session_views()
            return {"ok": True, "session_id": self.state.session_id}
        except Exception as extra:
            return {"ok": False, "error": str(extra)}

    def switch_chat_session(self, session_id: str) -> dict:
        try:
            if type(session_id) is not str or not session_id.strip():
                raise RuntimeError("切换对话需要 session_id。")
            sid = session_id.strip()
            known = {row["id"] for row in list_sessions()}
            if sid != self.state.session_id and sid not in known:
                raise RuntimeError("没有这条对话线程。")
            if self._agent_running:
                raise RuntimeError("凯尔希正在说话，等这句说完再切换对话。")
            self.state.session_id = sid
            self.state.save()
            self._reload_session_views()
            return {"ok": True, "session_id": sid, "items": list_chat(sid)}
        except Exception as extra:
            return {"ok": False, "error": str(extra)}

    def _reload_session_views(self) -> None:
        rows = list_chat(self.state.session_id)
        if self.agent is not None:
            self.agent.memory.clear()
        self._eval_bubble("load_history", rows=rows)
        self._eval_board(
            "load_thread",
            items=rows,
            session_id=self.state.session_id,
            sessions=list_sessions(),
        )

    def list_feishu_docs(self) -> dict:
        from .feishu_docs import list_my_docx

        try:
            return {"ok": True, "items": list_my_docx()}
        except Exception as extra:
            return {"ok": False, "error": str(extra)}

    def write_week_review_doc(self, payload: dict) -> dict:
        from .board_data import load_today_snapshot, save_today_fields
        from .feishu_docs import create_or_overwrite_markdown

        if not isinstance(payload, dict):
            return {"ok": False, "error": "写入参数必须是对象。"}
        try:
            snap = load_today_snapshot(refresh=False)
            markdown = (snap.get("summary") or "").strip()
            result = create_or_overwrite_markdown(
                markdown=markdown,
                doc=str(payload.get("doc") or ""),
                title=str(payload.get("title") or ""),
            )
            url = result.get("url") or ""
            if url:
                snap = save_today_fields(doc_url=url)
                if "新建" in str(result.get("message") or ""):
                    os.startfile(url)
            return {"ok": True, **snap, **result}
        except Exception as extra:
            return {"ok": False, "error": str(extra)}

    def send_board_chat(self, text: str, chips: dict | None = None) -> dict:
        if isinstance(chips, str):
            try:
                chips = json.loads(chips)
            except json.JSONDecodeError as extra:
                return {"ok": False, "error": f"点选参数不是合法 JSON。{extra}"}
        if chips is None:
            chips = {}
        if not isinstance(chips, dict):
            return {"ok": False, "error": "点选参数必须是对象。"}
        if self.pet is None:
            return {"ok": False, "error": "宠物还没就绪。"}
        if self.pet.busy or self._agent_running:
            return {"ok": False, "error": "凯尔希正在说话。"}
        try:
            maa = chips.get("maa")
            retro = chips.get("retro")
            if maa:
                if any(chips.get(key) for key in ("skills", "cli", "github", "retro")):
                    raise RuntimeError("方舟动作不能和技能、CLI、仓库或复盘同时点选。")
                return self._run_maa_chip(str(maa))
            if retro:
                raise RuntimeError(
                    "复盘请用对话「复盘」子界面生成或写入，不要和聊天混在一条发送里。"
                )
            message = self._compose_turn(text, chips)
            self.ui(lambda: self.send_chat(message, from_board=True))
            return {"ok": True}
        except Exception as extra:
            return {"ok": False, "error": str(extra)}

    def _run_maa_chip(self, action: str) -> dict:
        allowed = {key for key, _label in MAA_CHIPS}
        if action not in allowed:
            raise RuntimeError(f"没有方舟动作 {action!r}。")
        if action == "open_game":
            return self.maa_open_game()
        if action == "start_daily":
            return self.maa_start_daily()
        if action == "stop":
            return self.maa_stop()
        if action == "sync_skland":
            return self.sync_skland()
        if action == "today_farm":
            return self.compute_farm_plan()
        raise RuntimeError(f"没有方舟动作 {action!r}。")

    def _compose_turn(self, text: str, chips: dict) -> str:
        body = (text or "").strip()
        skills = chips.get("skills") or []
        cli = chips.get("cli") or []
        github = chips.get("github") or ""
        extra_keys = set(chips) - {"skills", "cli", "github", "maa", "retro"}
        if extra_keys:
            raise RuntimeError(f"不认识的点选：{', '.join(sorted(extra_keys))}。")
        if skills and (
            type(skills) is not list
            or any(type(x) is not str or not x.strip() for x in skills)
        ):
            raise RuntimeError("技能点选必须是非空字符串列表。")
        if cli and (
            type(cli) is not list or any(type(x) is not str or not x.strip() for x in cli)
        ):
            raise RuntimeError("CLI 点选必须是非空字符串列表。")
        if github and type(github) is not str:
            raise RuntimeError("仓库点选必须是字符串。")
        allowed_cli = {key for key, _label in CLI_CHIPS}
        for name in cli:
            if name not in allowed_cli:
                raise RuntimeError(f"没有 CLI 工具 {name!r}。")
        if any(name in NEED_REPO_TOOLS for name in cli) and not str(github).strip():
            raise RuntimeError("选了 GitHub 近况或路线图时必须同时选一个已列出的仓库。")
        if not body and not skills and not cli and not github:
            raise RuntimeError("输入框是空的。")
        if not skills and not cli and not github:
            return body
        lines = ["【本轮指定】"]
        for name in skills:
            lines.append(f"- 必须调用 read_skill，技能名 {name.strip()}")
        for name in cli:
            lines.append(f"- 必须调用工具 {name.strip()}")
        if str(github).strip():
            lines.append(
                f"- GitHub 仓库 {github.strip()}；github_recent / github_roadmap 必须用这个仓库"
            )
        prefix = "\n".join(lines)
        if body:
            return prefix + "\n\n" + body
        return prefix + "\n\n按上面的指定执行。"
