"""本机 gh：登录态、盯着的仓库状态、milestone roadmap、近期活动。"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import winreg
from datetime import datetime, timedelta, timezone

CREATE_NO_WINDOW = 0x08000000
TZ = timezone(timedelta(hours=8))
AUTH_HINT = "请在本机终端执行：gh auth login"
RECENT_DAYS = 14
REPO_LIST_LIMIT = 100
_PATH_MERGED = False


def list_owned_repos() -> list[dict]:
    raw = _run_gh_json(
        [
            "repo",
            "list",
            "--limit",
            str(REPO_LIST_LIMIT),
            "--json",
            "nameWithOwner,name,url,visibility,isPrivate,pushedAt,isFork,isArchived,description",
        ]
    )
    if type(raw) is not list:
        raise RuntimeError("gh repo list 必须返回数组。")
    if not raw:
        raise RuntimeError("这个 GitHub 账号下没有仓库。")
    if len(raw) >= REPO_LIST_LIMIT:
        raise RuntimeError(
            f"仓库不少于 {REPO_LIST_LIMIT} 个，列表被截断。归档或删掉不用的库后再刷新，不要靠桌宠猜漏了哪些。"
        )
    out = []
    for item in raw:
        if not isinstance(item, dict):
            raise RuntimeError("gh repo list 的每一项必须是对象。")
        if item.get("isArchived") is True:
            continue
        full = item.get("nameWithOwner")
        if type(full) is not str or full.count("/") != 1:
            raise RuntimeError("仓库缺少合法的 nameWithOwner。")
        out.append(
            {
                "full_name": full.strip(),
                "name": item.get("name") or full.split("/", 1)[1],
                "url": item.get("url") or "",
                "visibility": item.get("visibility") or "",
                "private": bool(item.get("isPrivate")),
                "pushed_at": item.get("pushedAt") or "",
                "fork": bool(item.get("isFork")),
                "description": item.get("description") or "",
            }
        )
    if not out:
        raise RuntimeError("没有未归档的仓库。")
    out.sort(key=lambda row: row["pushed_at"] or "", reverse=True)
    return out


def resolve_repo(name: str) -> str:
    if type(name) is not str or not name.strip():
        raise RuntimeError("仓库名必须是非空字符串。")
    want = name.strip()
    owned = [row["full_name"] for row in list_owned_repos()]
    if want in owned:
        return want
    hits = [item for item in owned if item.split("/", 1)[1].lower() == want.lower()]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise RuntimeError(f"仓库 {want!r} 不唯一。请用完整 owner/name：{', '.join(hits)}。")
    raise RuntimeError(
        f"仓库 {want!r} 不在当前 GitHub 账号的未归档仓库里。"
        f"当前有：{', '.join(owned)}。"
    )


def _merge_user_path() -> None:
    """Cursor 等宿主启动时 PATH 可能不含用户目录里的 gh。"""
    global _PATH_MERGED
    if _PATH_MERGED:
        return
    extra: list[str] = []
    hives = (
        (winreg.HKEY_CURRENT_USER, r"Environment"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
        ),
    )
    for root, sub in hives:
        try:
            with winreg.OpenKey(root, sub) as key:
                value, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            continue
        extra.extend(part.strip() for part in str(value).split(os.pathsep) if part.strip())
    expanded = [os.path.expandvars(part) for part in extra]
    current = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*expanded, current])
    _PATH_MERGED = True


def _gh_bin() -> str:
    _merge_user_path()
    found = shutil.which("gh")
    if found:
        return found
    raise RuntimeError(
        "找不到 gh。当前进程 PATH 和用户/系统 PATH 里都没有。"
        "请安装 GitHub CLI，并在本机终端执行 gh auth login。"
    )


def _run_gh(args: list[str], timeout: int = 60) -> str:
    creationflags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
    bin_path = _gh_bin()
    if bin_path.lower().endswith((".cmd", ".bat")):
        cmd = ["cmd", "/c", bin_path, *args]
    else:
        cmd = [bin_path, *args]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "找不到 gh。请确认已安装并在 PATH 中，然后执行 gh auth login。"
        ) from None
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh 超时（{timeout}s）。") from None
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(f"gh 失败（exit {completed.returncode}）。{AUTH_HINT}\n{err}")
    return completed.stdout


def _run_gh_json(args: list[str], timeout: int = 60):
    text = _run_gh(args, timeout=timeout).strip()
    if not text:
        raise RuntimeError(f"gh {' '.join(args)} 返回空。{AUTH_HINT}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh {' '.join(args)} 不是合法 JSON。") from exc


def auth_account() -> dict:
    user = _run_gh_json(["api", "user"])
    login = user.get("login")
    if type(login) is not str or not login.strip():
        raise RuntimeError(f"gh api user 没有 login。{AUTH_HINT}")
    return {"login": login.strip(), "name": user.get("name") or ""}


def repo_status(full_name: str, listed: dict | None = None) -> dict:
    prs = _run_gh_json(
        ["pr", "list", "--repo", full_name, "--state", "open", "--limit", "50", "--json", "number"]
    )
    issues = _run_gh_json(
        [
            "issue",
            "list",
            "--repo",
            full_name,
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,url,milestone",
        ]
    )
    if type(prs) is not list or type(issues) is not list:
        raise RuntimeError(f"{full_name} 的 PR/issue 列表必须是数组。")
    milestoned = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise RuntimeError(f"{full_name} 的 issue 项必须是对象。")
        milestone = issue.get("milestone")
        if not isinstance(milestone, dict):
            continue
        title = milestone.get("title")
        if type(title) is not str or not title.strip():
            continue
        milestoned.append(
            {
                "number": issue.get("number"),
                "title": issue.get("title") or "",
                "url": issue.get("url") or "",
                "milestone": title.strip(),
            }
        )
    groups: dict[str, list] = {}
    for item in milestoned:
        groups.setdefault(item["milestone"], []).append(item)
    roadmap_groups = [
        {"milestone": key, "issues": groups[key]}
        for key in sorted(groups)
    ]
    ci = _latest_run(full_name)
    meta = listed if isinstance(listed, dict) else {}
    name = meta.get("name") or full_name.split("/", 1)[1]
    private = bool(meta.get("private")) if listed is not None else False
    if listed is None:
        info = _run_gh_json(
            [
                "repo",
                "view",
                full_name,
                "--json",
                "name,url,visibility,isPrivate,pushedAt",
            ]
        )
        name = info.get("name") or name
        private = bool(info.get("isPrivate"))
        url = info.get("url") or ""
        visibility = info.get("visibility") or ""
        pushed_at = info.get("pushedAt") or ""
        description = ""
        fork = False
    else:
        url = meta.get("url") or ""
        visibility = meta.get("visibility") or ""
        pushed_at = meta.get("pushed_at") or ""
        description = meta.get("description") or ""
        fork = bool(meta.get("fork"))
    row = {
        "full_name": full_name,
        "name": name,
        "url": url,
        "visibility": visibility,
        "private": private,
        "fork": fork,
        "description": description,
        "pushed_at": pushed_at,
        "open_issue_count": len(issues),
        "open_pr_count": len(prs),
        "roadmap_count": len(milestoned),
        "loose_issue_count": len(issues) - len(milestoned),
        "ci": ci,
        "roadmap": roadmap_groups,
        "roadmap_hint": (
            ""
            if roadmap_groups
            else "没有带 milestone 的未关闭 issue。到 GitHub 建 milestone，并把要做的 issue 挂上。"
        ),
    }
    row.update(_summarize_repo(row))
    return row


def _summarize_repo(repo: dict) -> dict:
    """根据未关闭 issue / milestone 写一句状态，不编没出现的功能。"""
    name = repo["name"]
    road = repo["roadmap"]
    prs = repo["open_pr_count"]
    loose = repo["loose_issue_count"]
    if not road:
        phase = "no_roadmap"
        label = "无路线图"
        text = (
            f"{name} 还没有挂 milestone 的未关闭 issue，无法从路线图判断开发状态。"
        )
        if repo["open_issue_count"]:
            text += f"另有 {repo['open_issue_count']} 条未进路线图的 issue。"
        if prs:
            text += f"未关闭 PR {prs} 个。"
        return {"phase": phase, "phase_label": label, "summary": text}
    miles = [group["milestone"] for group in road]
    titles = [issue["title"] for group in road for issue in group["issues"] if issue.get("title")]
    shown = "；".join(titles[:4])
    extra = ""
    if len(titles) > 4:
        extra = f" 其余 {len(titles) - 4} 条未列出。"
    text = f"{name} 当前 milestone：{'、'.join(miles)}。路线图未关闭 {len(titles)} 条：{shown}。{extra}".strip()
    if loose:
        text += f"另有 {loose} 条 issue 没有挂 milestone。"
    if prs:
        text += f"未关闭 PR {prs} 个。"
    return {"phase": "in_progress", "phase_label": "进行中", "summary": text}


def _latest_run(full_name: str) -> dict:
    runs = _run_gh_json(
        [
            "run",
            "list",
            "--repo",
            full_name,
            "--limit",
            "1",
            "--json",
            "conclusion,status,name,updatedAt,url,displayTitle,headBranch",
        ]
    )
    if type(runs) is not list:
        raise RuntimeError(f"{full_name} 的 Actions 列表必须是数组。")
    if not runs:
        return {"present": False, "hint": "没有 GitHub Actions 记录。"}
    item = runs[0]
    if not isinstance(item, dict):
        raise RuntimeError(f"{full_name} 的 Actions 项必须是对象。")
    return {
        "present": True,
        "name": item.get("name") or "",
        "title": item.get("displayTitle") or "",
        "status": item.get("status") or "",
        "conclusion": item.get("conclusion") or "",
        "updated_at": item.get("updatedAt") or "",
        "url": item.get("url") or "",
        "branch": item.get("headBranch") or "",
    }


def board_snapshot() -> dict:
    account = auth_account()
    repos = []
    for listed in list_owned_repos():
        repos.append(repo_status(listed["full_name"], listed))
    return {
        "ok": True,
        "login": account["login"],
        "user_name": account["name"],
        "repos": repos,
    }


def format_status_text() -> str:
    snap = board_snapshot()
    lines = [f"gh 已登录：{snap['login']}"]
    if snap["user_name"]:
        lines[0] += f"（{snap['user_name']}）"
    lines.append(f"未归档仓库 {len(snap['repos'])} 个。")
    for repo in snap["repos"]:
        vis = "私有" if repo["private"] else "公开"
        lines.append("")
        lines.append(f"## {repo['full_name']}（{vis} · {repo.get('phase_label') or ''}）")
        lines.append(repo.get("summary") or "")
        lines.append(f"地址：{repo['url']}")
        lines.append(f"上次推送：{repo['pushed_at'] or '无'}")
        lines.append(
            f"未关闭 PR：{repo['open_pr_count']}；未关闭 issue：{repo['open_issue_count']}；"
            f"路线图：{repo['roadmap_count']}"
        )
        ci = repo["ci"]
        if ci.get("present"):
            lines.append(
                f"最近 CI：{ci.get('name') or ci.get('title')} "
                f"{ci.get('status')}/{ci.get('conclusion') or '无结论'} {ci.get('updated_at')}"
            )
        else:
            lines.append(f"最近 CI：{ci.get('hint') or '没有'}")
    return "\n".join(lines)


def format_roadmap_text(repo_name: str) -> str:
    full = resolve_repo(repo_name)
    repo = repo_status(full)
    lines = [f"# {full} roadmap", repo.get("summary") or ""]
    if not repo["roadmap"]:
        lines.append(repo["roadmap_hint"])
        return "\n".join(lines)
    for group in repo["roadmap"]:
        lines.append(f"## {group['milestone']}")
        for issue in group["issues"]:
            lines.append(f"- #{issue['number']} {issue['title']} {issue['url']}")
    return "\n".join(lines)


def format_recent_text(repo_name: str) -> str:
    full = resolve_repo(repo_name)
    since = (datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    commits = _run_gh_json(
        [
            "api",
            f"repos/{full}/commits?since={since}&per_page=20",
        ]
    )
    if type(commits) is not list:
        raise RuntimeError(f"{full} 的 commit 列表必须是数组。")
    prs = _run_gh_json(
        [
            "pr",
            "list",
            "--repo",
            full,
            "--state",
            "all",
            "--limit",
            "20",
            "--json",
            "number,title,url,state,mergedAt,closedAt,updatedAt,createdAt",
        ]
    )
    issues = _run_gh_json(
        [
            "issue",
            "list",
            "--repo",
            full,
            "--state",
            "all",
            "--limit",
            "20",
            "--json",
            "number,title,url,state,updatedAt,createdAt,closedAt,milestone",
        ]
    )
    if type(prs) is not list or type(issues) is not list:
        raise RuntimeError(f"{full} 的近期 PR/issue 必须是数组。")
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_DAYS)
    lines = [f"# {full} 近 {RECENT_DAYS} 天", f"since={since}"]
    lines.append("## commits")
    if not commits:
        lines.append("无")
    for item in commits:
        if not isinstance(item, dict):
            raise RuntimeError(f"{full} 的 commit 项必须是对象。")
        sha = str(item.get("sha") or "")[:7]
        commit = item.get("commit") if isinstance(item.get("commit"), dict) else {}
        message = str((commit or {}).get("message") or "").split("\n", 1)[0]
        date = ""
        author = commit.get("author") if isinstance(commit.get("author"), dict) else {}
        if author:
            date = str(author.get("date") or "")
        lines.append(f"- {sha} {date} {message}")
    lines.append("## pull requests")
    recent_prs = [item for item in prs if isinstance(item, dict) and _within(item, cutoff)]
    if not recent_prs:
        lines.append("无")
    for item in recent_prs:
        lines.append(
            f"- #{item.get('number')} [{item.get('state')}] {item.get('title')} {item.get('url')}"
        )
    lines.append("## issues")
    recent_issues = [item for item in issues if isinstance(item, dict) and _within(item, cutoff)]
    if not recent_issues:
        lines.append("无")
    for item in recent_issues:
        milestone = item.get("milestone")
        mile = ""
        if isinstance(milestone, dict) and type(milestone.get("title")) is str:
            mile = f" milestone={milestone['title']}"
        lines.append(
            f"- #{item.get('number')} [{item.get('state')}] {item.get('title')}{mile} {item.get('url')}"
        )
    return "\n".join(lines)


def _within(item: dict, cutoff: datetime) -> bool:
    stamps = []
    for key in ("updatedAt", "createdAt", "mergedAt", "closedAt"):
        raw = item.get(key)
        if type(raw) is str and raw.strip():
            stamps.append(raw.strip())
    if not stamps:
        return False
    for raw in stamps:
        parsed = _parse_iso(raw)
        if parsed is not None and parsed >= cutoff:
            return True
    return False


def _parse_iso(raw: str) -> datetime | None:
    text = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
