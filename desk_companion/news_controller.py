"""固定资讯工作流的本地 API：预览、发布及定时调度共用独立任务。"""
from datetime import datetime
from .memory import TZ
from . import news
from .tasks import TERMINAL


def snapshot():
    return {"ok": True, "settings": news.load_settings(), "runs": news.list_runs()}


def check():
    from .news_publish import validate_targets
    cfg = news.load_settings()
    targets = validate_targets(cfg)
    cfg["base_token"] = targets["base_token"]
    news.atomic_json(news.settings_path(), cfg)
    return {"ok": True, "targets": targets, "settings": cfg}


def start(host, *, publish=False, run_id="", job_id="", seconds=900, attempt=0, send_group=True):
    if type(publish) is not bool or type(send_group) is not bool:
        raise ValueError("发布设置必须为开关。")
    cfg = news.load_settings()
    day = datetime.now(TZ).date().isoformat()
    if run_id:
        run = news.load_run(run_id)
        if not run or not run.get("report"):
            raise ValueError("请先生成日报预览。")
        cfg, day = run["settings"], run["day"]
        if run_id != news.run_id_for(day, news.load_settings()):
            raise ValueError("推送位置已经改变，请重新生成预览并检查。")
    if publish and not all(cfg[k] for k in ("profile", "wiki_url", "base_url", "table_id")):
        raise ValueError("请先设置应用、知识库和资讯表。")
    rid = run_id or news.run_id_for(day, cfg)
    manager = host.tasks
    with manager.cv:
        # 重复点击返回同一任务；不同日期/目标可在会话队列中等待。
        for task in manager.list("automation")["items"]:
            if task["state"] not in TERMINAL and task["source"].get("run_id") == rid:
                return {"ok": True, "task_id": task["id"], "run_id": rid}
        task_id = manager.submit("AI/Agent 工程日报 · " + day + ("（发布）" if publish else "（预览）"), "news-" + news.digest(cfg), "automation",
            source={"workflow": "ai_news", "run_id": rid, "job_id": job_id, "attempt": attempt},
            task_limits={"call_timeout": min(120, seconds), "task_timeout": seconds}, workflow="ai_news",
            news_settings=cfg, news_day=day, news_run_id=rid, news_publish=publish, news_send_group=send_group)
    return {"ok": True, "task_id": task_id, "run_id": rid}
