"""视频工作区复用受监督任务，保留既有桌面与飞书视频记录。"""
import uuid

from .video import normalize_url


def task_ids(manager):
    with manager.db() as db:
        return [row[0] for row in db.execute(
            "SELECT t.id FROM tasks t WHERE json_extract(t.source, '$.workflow')='video' "
            "OR t.id IN (SELECT e.task FROM events e WHERE e.kind='tool_start' "
            "AND json_extract(e.data, '$.tool') IN ('read_video','read_video_transcript','save_video_summary')) "
            "ORDER BY t.created DESC LIMIT 100")]


def snapshot(host):
    return {"ok": True, "items": [host.tasks.get(task_id, False) for task_id in task_ids(host.tasks)]}


def start(host, url):
    _, canonical = normalize_url(url)
    session = "video-" + uuid.uuid4().hex
    text = ("请读取并用中文总结这个视频：" + canonical +
            "\n先调用 read_video，依据实际字幕总结核心观点、技术细节与带时间点的出处。"
            "未取得字幕时只说明实际取得的元数据和局限；这次只读取和总结，不要保存、写入或执行其它修改。")
    task_id = host.tasks.submit(text, session, "video", source={"workflow": "video", "video_url": canonical})
    host._focused_task = task_id
    return {"ok": True, "task_id": task_id}


def continue_task(host, task_id, text):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("请填写有效追问。")
    # 新工作区和既有视频任务均可追问，普通聊天不能被伪装成视频记录。
    if task_id not in task_ids(host.tasks):
        raise ValueError("请选择已有的视频任务。")
    parent = host.tasks.get(task_id, False)
    original = parent["source"].get("video_url")
    if original:
        # 排队时取消或模型调用前失败，原链接还没有写入聊天历史。
        text = "当前会话原视频：" + original + "\n\n用户追问：" + text
    found = host.tasks.resume(task_id, text, send_back=False)
    host.tasks.update_source(found, workflow="video")
    host._focused_task = found
    return {"ok": True, "task_id": found}
