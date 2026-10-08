"""真实子进程验证：硬超时、取消、并行及会话顺序。不调用线上模型。"""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from desk_companion.tasks import TaskManager

WORKER = '''import json,sys,time
r=json.loads(sys.stdin.readline())
def emit(k,d):
 print(json.dumps(dict(kind=k,data=d)),flush=True)
emit('token','保留片段')
if r['text']=='timeout':
 emit('llm_start',{})
 time.sleep(10)
elif r['text']=='slow': time.sleep(.7)
elif r['text']=='tool':
 emit('tool_start',dict(tool='create_calendar_event',step='s1'))
 emit('tool_end',dict(tool='create_calendar_event',step='s1',status='success'))
emit('result',r['text'])
'''


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DESK_COMPANION_DATA_DIR": self.temp.name})
        self.env.start()
        self.worker = Path(self.temp.name) / "worker.py"
        self.worker.write_text(WORKER, "utf-8")
        self.manager = TaskManager(path=Path(self.temp.name) / "tasks.sqlite3", command=[sys.executable, "-u", str(self.worker)])

    def tearDown(self):
        self.manager.shutdown()
        deadline = time.time() + 5
        while self.manager.active and time.time() < deadline:
            time.sleep(.05)
        self.env.stop()
        self.temp.cleanup()

    def test_parallel_and_same_session_fifo(self):
        first = self.manager.submit("slow", "a")
        second = self.manager.submit("second", "a")
        other = self.manager.submit("other", "b")
        self.assertEqual(self.manager.wait(other)["answer"], "other")
        self.assertNotIn(self.manager.get(first)["state"], {"succeeded", "failed"})
        self.assertEqual(self.manager.get(second)["state"], "queued")
        a = self.manager.wait(first)
        b = self.manager.wait(second)
        self.assertGreaterEqual(b["started"], a["ended"])

    def test_hard_call_timeout_keeps_partial(self):
        self.manager.settings.update(call_timeout=.2, task_timeout=3)
        started = time.monotonic()
        task = self.manager.wait(self.manager.submit("timeout", "a"))
        self.assertEqual(task["state"], "timed_out")
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(task["answer"], "保留片段")

    def test_cancel_running_and_queued(self):
        first = self.manager.submit("timeout", "a")
        second = self.manager.submit("next", "a")
        deadline = time.time() + 2
        while not self.manager.get(first)["answer"] and time.time() < deadline:
            time.sleep(.02)
        self.manager.cancel(second)
        self.manager.cancel(first)
        self.assertEqual(self.manager.wait(first)["state"], "cancelled")
        self.assertEqual(self.manager.wait(second)["state"], "cancelled")

    def test_restart_never_replays_and_resume_carries_steps(self):
        task = self.manager.wait(self.manager.submit("tool", "a"))
        resumed = self.manager.resume(task["id"], "请继续")
        with self.manager.db() as db:
            payload = json.loads(db.execute("SELECT request FROM tasks WHERE id=?", (resumed,)).fetchone()[0])
        self.assertIn("create_calendar_event", payload["resume_note"])
        self.assertIn("不可盲目重做", payload["resume_note"])
        self.manager.wait(resumed)
        with self.manager.db() as db:
            db.execute("UPDATE tasks SET state='running' WHERE id=?", (task["id"],))
            db.commit()
        self.manager.shutdown()
        self.manager.scheduler.join(1)
        self.manager = TaskManager(path=self.manager.path, command=[sys.executable, "-u", str(self.worker)])
        self.assertEqual(self.manager.get(task["id"])["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
