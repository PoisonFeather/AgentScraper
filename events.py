# events.py
import queue
import time
import uuid
import threading
from typing import Optional

_lock = threading.Lock()
_runs: dict[str, queue.Queue] = {}

def create_run() -> str:
    run_id = uuid.uuid4().hex
    with _lock:
        _runs[run_id] = queue.Queue()
    return run_id

def get_queue(run_id: str) -> Optional[queue.Queue]:
    with _lock:
        return _runs.get(run_id)

def emit(run_id: str | None, typ: str, data: dict):
    if not run_id:
        return
    q = get_queue(run_id)
    if not q:
        return
    q.put({"type": typ, "data": data, "ts": time.time()})

def close_run(run_id: str):
    emit(run_id, "done", {})
    with _lock:
        _runs.pop(run_id, None)
