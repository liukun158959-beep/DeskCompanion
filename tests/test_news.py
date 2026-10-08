"""资讯流程的来源约束、补跑、隔离、恢复与去重；不操作真实账号。"""
import json
import os
import tempfile
import threading
import sys
import asyncio
import unittest
from email.message import Message
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desk_companion import automation, news, news_controller, news_publish
from desk_companion.memory import TZ


def fixture():
    cfg = {**news.DEFAULTS, "profile": "test", "wiki_url": "https://example.feishu.cn/wiki/testwiki",
           "base_url": "https://example.feishu.cn/base/testbase", "base_token": "testbase", "table_id": "tbltest", "chat_id": "oc_test"}
    day = "2026-10-08"
    items = [{"id": news.digest(str(i)), "title": f"官方技术 {i}", "url": f"https://github.com/example/project{i}",
              "summary": "已核实功能", "value": "建议先测试", "caution": "尚未在项目验证", "category": "Agent 工程", "published": day, "date_verified": True} for i in range(3)]
    return {"id": news.run_id_for(day, cfg), "day": day, "settings": cfg, "receipts": {}, "warnings": [],
            "status": "draft", "report": {"lead": "三项工具能力值得试用", "items": items, "candidate_count": 12}}


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"DESK_COMPANION_DATA_DIR": str(self.root)}).start()

    def test_unknown_links_duplicate_sources_and_private_urls_are_rejected(self):
        candidates = [{"id": "known", "title": "官方说明", "url": "https://github.com/example/repo", "published": "", "date_verified": False}]
        value = {"lead": "重点", "items": [{"source_id": "invented", "category": "工程", "summary": "编造", "value": "测试"}] * 3}
        with self.assertRaises(ValueError):
            news.validate_report(value, candidates, 5)
        value["items"] = [{"source_id": "known", "category": "工程", "summary": "功能", "value": "测试"}] * 3
        with self.assertRaises(ValueError):
            news.validate_report(value, candidates, 5)
        for url in ("https://localhost/test", "http://github.com/test", "https://github.com.evil.invalid/test", "https://user:pass@github.com/test", "https://github.com:8080/test"):
            self.assertFalse(news.primary_url(url))
        self.assertEqual(news.primary_url("https://github.com/example/repo#readme"), "https://github.com/example/repo")

    def test_preview_never_calls_publisher_and_retains_verified_sources(self):
        run = fixture()
        events = []
        request = {"news_settings": run["settings"], "news_day": run["day"], "news_run_id": run["id"], "news_publish": False}
        with patch.object(news, "collect", return_value=([{"id": "source"}] * 3, ["某来源不可读"])), \
             patch.object(news, "summarize", return_value=run["report"]), patch.object(news_publish, "publish") as publish:
            news.execute(request, lambda kind, data: events.append((kind, data)))
        publish.assert_not_called()
        saved = news.load_run(run["id"])
        self.assertEqual(saved["status"], "draft")
        self.assertEqual(len(saved["candidates"]), 3)
        self.assertEqual(events[-1][0], "result")

    def test_failed_collection_keeps_diagnostics_without_publishing(self):
        run = fixture()
        request = {"news_settings": run["settings"], "news_day": run["day"], "news_run_id": run["id"]}
        with patch.object(news, "collect", return_value=([{"id": "one"}], ["官方源超时"])), patch.object(news, "summarize") as summarize:
            news.execute(request, lambda *_: None)
        summarize.assert_not_called()
        saved = news.load_run(run["id"])
        self.assertEqual(saved["warnings"], ["官方源超时"])
        self.assertEqual(saved["status"], "failed")
        self.assertEqual(saved["candidates"], [{"id": "one"}])

    def test_search_index_date_is_not_treated_as_verified_publication(self):
        cfg = {**news.DEFAULTS, "topics": ["Agent"]}
        payload = {"results": [{"title": "Official", "link": "https://github.com/example/repo", "published_date": "2026-10-08"}]}
        with patch("desk_companion.envconf.require_llm_env", return_value={"ATLAS_BASE_URL": "https://example.invalid/v1", "ATLAS_API_KEY": "test"}), \
             patch("desk_companion.web_search._post", return_value=payload), \
             patch("desk_companion.web_search.format_search"), \
             patch.object(news, "fetch_source", return_value={"text": "official article", "published": ""}):
            rows, _ = news.collect("2026-10-08", cfg, lambda *_: None)
        self.assertFalse(rows[0]["date_verified"])
        self.assertEqual(rows[0]["published"], "")

    def test_publication_date_comes_from_official_metadata_or_arxiv_version(self):
        htmls = [('<meta name="ms.date" content="2026-10-02T00:00:00Z"><p>Official documentation</p>',
                  "https://learn.microsoft.com/en-us/test", "2026-10-02T00:00:00Z"),
                 ('<p>arXiv:2610.04116v1 [cs.AI] 02 Oct 2026</p><p>Other example date: 01 Jan 2000</p>',
                  "https://arxiv.org/html/2610.04116v1", "2026-10-02")]
        for html, url, expected in htmls:
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.headers = Message()
            response.headers['Content-Type'] = 'text/html; charset=utf-8'
            response.read.return_value = html.encode()
            opener = Mock()
            opener.open.return_value = response
            with patch.object(news.urllib.request, "build_opener", return_value=opener):
                self.assertEqual(news.fetch_source(url)["published"], expected)

    def test_latest_missed_slot_runs_once_without_replaying_days(self):
        base = dict(name="日报", action="ai_news", enabled=True, cadence="daily", weekdays=[], hour=9, minute=0)
        automation.upsert_job(base)
        store = automation.load_store()
        job = store["jobs"][0]
        now = datetime(2026, 10, 8, 14, 0, tzinfo=TZ)
        job["created_at"] = (now - timedelta(days=10)).isoformat()
        store["last_alive_at"] = (now - timedelta(days=5)).isoformat()
        self.assertFalse(automation._mark_missed(store, now))
        self.assertEqual(automation._due_jobs(store, now), [job])
        latest = automation._latest_slot(now, job)
        self.assertEqual(latest, now.replace(hour=9))
        job["last_run_slot"] = automation._slot_key(latest, job)
        self.assertEqual(automation._due_jobs(store, now), [])
        job["last_result"] = "running"
        self.assertTrue(automation._abandon_queued(store))
        self.assertEqual(automation._due_jobs(store, now), [job])

    def test_disabled_new_jobs_and_legacy_actions_do_not_catch_up(self):
        now = datetime(2026, 10, 8, 14, tzinfo=TZ)
        for action in ("ai_news", "maa_daily"):
            automation.upsert_job(dict(name=action, action=action, enabled=False, cadence="daily", weekdays=[], hour=9, minute=0))
        store = automation.load_store()
        self.assertFalse(automation._due_jobs(store, now))
        store["jobs"][1].update(enabled=True, created_at=(now - timedelta(days=3)).isoformat())
        self.assertFalse(automation._due_jobs(store, now))

    def test_document_response_loss_reconciles_by_title_without_new_document(self):
        run = fixture()
        target = {"space_id": "123", "node_token": "parent"}
        workspace = self.root / "draft-unique"
        workspace.mkdir()
        draft = workspace / "draft.xml"
        created = []
        def save(**fields):
            run.update(fields)
        def cli(_cfg, args, **kwargs):
            if args[:2] == ["wiki", "+node-list"]:
                return {"nodes": created, "has_more": False}
            if "init-draft" in args:
                return {"workspace": "draft-unique", "draft_path": "draft-unique/draft.xml"}
            if "parse" in args:
                return {"assessment": {"status": "passed"}}
            if args[:2] == ["docs", "+create"]:
                created.append({"title": news_publish.doc_title(run), "obj_type": "docx", "obj_token": "doc-created", "node_token": "wiki-created"})
                raise news_publish.PublishError("连接中断，回执丢失")
            self.fail(args)
        with patch.object(news_publish, "cli", side_effect=cli):
            with self.assertRaises(news_publish.PublishError):
                news_publish.create_document(run, target, save, lambda *_: None)
            self.assertTrue(run["receipts"]["doc_pending"])
            self.assertFalse(workspace.exists())
            news_publish.create_document(run, target, save, lambda *_: None)
        self.assertEqual(run["doc_id"], "doc-created")
        self.assertEqual(len(created), 1)

    def test_record_response_loss_reconciles_exact_key_and_never_recreates(self):
        run = fixture()
        run["doc_url"] = "https://example.feishu.cn/docx/test"
        records = []
        creates = []
        def cli(_cfg, args, **kwargs):
            if args[1] == "+record-search":
                self.assertIn("--filter-json", args)
                return {"records": records}
            creates.append(args)
            records.append({"id": "rec_created"})
            raise news_publish.PublishError("响应丢失")
        with patch.object(news_publish, "cli", side_effect=cli):
            with self.assertRaises(news_publish.PublishError):
                news_publish.ensure_record(run, run["report"]["items"][0], "base", lambda **kw: run.update(kw), lambda *_: None)
            news_publish.ensure_record(run, run["report"]["items"][0], "base", lambda **kw: run.update(kw), lambda *_: None)
        self.assertEqual(len(creates), 1)
        self.assertEqual(list(run["receipts"]["records"].values()), ["rec_created"])

    def test_unknown_record_result_without_match_does_not_write_again(self):
        run = fixture()
        key = news.digest([run["day"], run["report"]["items"][0]["url"]])
        run["receipts"]["records_pending"] = [key]
        with patch.object(news_publish, "cli", return_value={"records": []}) as cli:
            with self.assertRaises(news_publish.PublishError):
                news_publish.ensure_record(run, run["report"]["items"][0], "base", lambda **kw: None, lambda *_: None)
        self.assertEqual(cli.call_count, 1)

    def test_typed_base_ack_without_id_is_reconciled_and_never_duplicated(self):
        run = fixture()
        run["doc_url"] = "https://example.feishu.cn/docx/doc"
        with patch.object(news_publish, "cli", side_effect=[{"record_id_list": [], "has_more": False},
                {"created": True, "record": {"create": {"状态": "已归档"}}},
                {"record_id_list": ["rec_typed"], "has_more": False}]) as cli:
            news_publish.ensure_record(run, run["report"]["items"][0], "base", lambda **kw: run.update(kw), lambda *_: None)
            news_publish.ensure_record(run, run["report"]["items"][0], "base", lambda **kw: run.update(kw), lambda *_: None)
        self.assertEqual(cli.call_count, 3)
        self.assertEqual(list(run["receipts"]["records"].values()), ["rec_typed"])
        self.assertEqual(run["receipts"]["records_pending"], [])

    def test_group_send_expired_idempotency_window_requires_reconciliation(self):
        run = fixture()
        run.update(doc_id="doc", doc_url="https://example.feishu.cn/docx/doc")
        run["receipts"] = {"doc_verified": True, "image_key": "img_v3_test", "message_pending_at": 1,
                           "records": {news.digest([run["day"], i["url"]]): "rec" for i in run["report"]["items"]}}
        with patch.object(news_publish, "validate_targets", return_value={"base_token": "base"}), \
             patch.object(news_publish, "render_cover", return_value=self.root / "image.png"), patch.object(news_publish, "cli") as cli:
            with self.assertRaises(news_publish.PublishError):
                news_publish.publish(run, lambda **kw: run.update(kw), lambda *_: None)
        cli.assert_not_called()

    def test_card_has_image_grouped_evidence_and_correct_target_links(self):
        run = fixture()
        run["doc_url"] = "https://example.feishu.cn/docx/doc"
        card = news_publish.news_card(run, "img_v3_test")
        self.assertEqual(card["schema"], "2.0")
        self.assertEqual(len(card["body"]["elements"]), 3)
        raw = json.dumps(card)
        self.assertIn("img_v3_test", raw)
        self.assertIn(run["doc_url"], raw)
        for item in run["report"]["items"]:
            self.assertIn(item["url"], raw)
        image = news_publish.render_cover(run)
        from PIL import Image
        with Image.open(image) as img:
            self.assertEqual(img.size, (1200, 640))

    def test_controller_rejects_changed_targets_before_submit(self):
        run = fixture()
        news.atomic_json(news.run_path(run["id"]), run)
        changed = {**run["settings"], "chat_id": "oc_other"}
        with patch.object(news, "load_settings", return_value=changed):
            with self.assertRaises(ValueError):
                news_controller.start(Mock(), publish=True, run_id=run["id"])

    def test_manual_preview_submits_fixed_workflow_and_fifteen_minute_limit(self):
        run = fixture()
        manager = Mock()
        manager.cv = threading.Condition(threading.RLock())
        manager.list.return_value = {"items": []}
        manager.submit.return_value = "task"
        with patch.object(news, "load_settings", return_value=run["settings"]):
            started = news_controller.start(SimpleNamespace(tasks=manager), publish=False)
        self.assertEqual(started["task_id"], "task")
        req = manager.submit.call_args.kwargs
        self.assertEqual(req["workflow"], "ai_news")
        self.assertFalse(req["news_publish"])
        self.assertEqual(req["task_limits"]["task_timeout"], 900)

    def test_background_news_poll_does_not_steal_chat_progress_focus(self):
        from desk_companion.bridge import Bridge
        manager = Mock()
        manager.get.return_value = {"session": "news"}
        host = SimpleNamespace(tasks=manager, _focused_task="chat")
        with patch("desk_companion.memory.list_chat", return_value=[]):
            Bridge(host).get_agent_task("news-task", focus=False)
            self.assertEqual(host._focused_task, "chat")
            Bridge(host).get_agent_task("news-task")
            self.assertEqual(host._focused_task, "news-task")

    def test_target_validation_rejects_wrong_fields_before_any_write(self):
        run = fixture()
        with patch.object(news_publish, "cli", side_effect=[{"space_id": "1", "node_token": "wiki"}, {"base_token": "base"},
                    {"fields": [{"name": name, "type": "number"} for name in news.FIELDS]}]) as cli:
            with self.assertRaises(ValueError):
                news_publish.validate_targets(run["settings"])
        self.assertEqual(cli.call_count, 3)

    def test_real_worker_creates_preview_without_cli_or_shared_chat_history(self):
        from desk_companion.tasks import TaskManager
        run = fixture()
        manager = TaskManager(command=[sys.executable, "-u", "-c", "exec(open('tests/news_worker_fixture.py',encoding='utf-8').read())"])
        self.addCleanup(manager.shutdown)
        task_id = manager.submit("预览", "news-isolated", "automation", workflow="ai_news",
            news_settings=run["settings"], news_day=run["day"], news_run_id=run["id"], news_publish=False,
            task_limits={"call_timeout": 90, "task_timeout": 900})
        result = manager.wait(task_id)
        self.assertEqual(result["state"], "succeeded")
        self.assertIn("离线流程正常", result["answer"])
        self.assertEqual(news.load_run(run["id"])["status"], "draft")
        self.assertFalse((self.root / "memory/chat.jsonl").exists())

    def test_independent_news_can_start_while_legacy_host_is_busy(self):
        scheduler = automation.AutomationScheduler(SimpleNamespace(_agent_running=True))
        scheduler._queued = {"maa_daily": "maa", "ai_news": "news"}
        with patch.object(scheduler, "_execute") as execute, patch.object(scheduler, "_notify"):
            scheduler._loop()
        execute.assert_called_once_with("news")
        self.assertEqual(scheduler._queued, {"maa_daily": "maa"})

    def test_scheduled_retry_once_shares_remaining_fifteen_minute_budget(self):
        run = fixture()
        manager = Mock()
        manager.get.side_effect = [dict(state="failed", started=__import__('time').time(), error="临时错误"),
                                   dict(state="succeeded", started=__import__('time').time(), error="")]
        scheduler = automation.AutomationScheduler(SimpleNamespace(tasks=manager))
        with patch.object(news, "load_run", return_value={"retryable": True}), \
             patch.object(news_controller, "start", return_value={"task_id": "retry"}) as start, \
             patch.object(scheduler, "_news_result") as result:
            scheduler._monitor_news("job", {"task_id": "first", "run_id": run["id"]})
        start.assert_called_once()
        self.assertEqual(start.call_args.kwargs["attempt"], 1)
        self.assertLess(start.call_args.kwargs["seconds"], 900)
        self.assertEqual(result.call_args.args[:2], ("job", "ok"))


class SchedulerApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_cover_requires_auth_and_rejects_traversal(self):
        from desk_companion.local_api import server
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"DESK_COMPANION_DATA_DIR": folder}), patch.object(server, "TOKEN", "test"):
            connection = SimpleNamespace(respond=lambda code, body: SimpleNamespace(status_code=code, body=body))
            rid = "a" * 32
            cover = news.run_path(rid).with_suffix(".png")
            cover.parent.mkdir(parents=True)
            cover.write_bytes(b'png test')
            self.assertEqual(server._news_cover(connection, f"/news-cover/{rid}").status_code, 401)
            self.assertEqual(server._news_cover(connection, "/news-cover/../../secret?token=test").status_code, 404)
            self.assertEqual(server._news_cover(connection, f"/news-cover/{rid}?token=test").body, b'png test')

    async def test_headless_api_drives_and_stops_scheduler(self):
        from desk_companion.local_api.server import scheduled_jobs
        shutdown = asyncio.Event()
        loop = asyncio.get_running_loop()
        ticks = []
        def tick():
            ticks.append(1)
            loop.call_soon_threadsafe(shutdown.set)
        await asyncio.wait_for(scheduled_jobs(SimpleNamespace(automation=SimpleNamespace(tick=tick)), shutdown), 3)
        self.assertEqual(ticks, [1])


if __name__ == "__main__":
    unittest.main()
