import json
import uuid
import threading
from datetime import datetime
from pathlib import Path

from config import Config

_lock = threading.Lock()


def _read_json(path: Path, default):
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _write_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class StateManager:

    # ── Processed URLs ────────────────────────────────────────────────────────

    @staticmethod
    def get_processed_urls() -> set:
        data = _read_json(Config.PROCESSED_FILE, [])
        return set(data)

    @staticmethod
    def mark_processed(url: str):
        with _lock:
            processed = _read_json(Config.PROCESSED_FILE, [])
            if url not in processed:
                processed.append(url)
            _write_json(Config.PROCESSED_FILE, processed)

    # ── Jobs ──────────────────────────────────────────────────────────────────

    @staticmethod
    def get_jobs(limit: int = 50) -> list:
        jobs = _read_json(Config.JOBS_FILE, [])
        return list(reversed(jobs[-limit:]))  # newest first

    @staticmethod
    def add_job(url: str | None, source: str) -> str:
        job_id = str(uuid.uuid4())[:8]
        with _lock:
            jobs = _read_json(Config.JOBS_FILE, [])
            jobs.append({
                "id": job_id,
                "url": url,
                "source": source,
                "status": "queued",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "results": [],
                "error": None,
            })
            if len(jobs) > 200:
                jobs = jobs[-200:]
            _write_json(Config.JOBS_FILE, jobs)
        return job_id

    @staticmethod
    def update_job(job_id: str, **kwargs):
        with _lock:
            jobs = _read_json(Config.JOBS_FILE, [])
            for job in jobs:
                if job["id"] == job_id:
                    job.update(kwargs)
                    job["updated_at"] = datetime.now().isoformat()
                    break
            _write_json(Config.JOBS_FILE, jobs)

    @staticmethod
    def get_job(job_id: str) -> dict | None:
        jobs = _read_json(Config.JOBS_FILE, [])
        for job in jobs:
            if job["id"] == job_id:
                return job
        return None
