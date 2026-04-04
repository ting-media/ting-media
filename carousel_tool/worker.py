"""
Background worker: processes job queue and runs scheduled scans.
Runs in a daemon thread alongside the Flask app.
"""

import logging
import threading
import time

import schedule

from config import Config
from state_manager import StateManager

logger = logging.getLogger(__name__)

_instance = None
_instance_lock = threading.Lock()


class Worker:

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._queue: list[dict] = []
        self._queue_lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="carousel-worker")
        self._thread.start()
        self._setup_schedule()
        logger.info("Worker thread started")

    def stop(self):
        self._stop_event.set()
        schedule.clear()
        logger.info("Worker stopped")

    def refresh_schedule(self):
        """Reload scan schedule from Config (call after settings change)."""
        self._setup_schedule()

    def _setup_schedule(self):
        schedule.clear()
        for t in Config.scan_times():
            schedule.every().day.at(t).do(self._scheduled_scan)
            logger.info("Scheduled daily scan at %s", t)

    def _scheduled_scan(self):
        self.enqueue_scan(source="scheduled")

    # ── Queue API ─────────────────────────────────────────────────────────

    def enqueue_url(self, url: str) -> str:
        """Add a single URL to the processing queue. Returns job_id."""
        job_id = StateManager.add_job(url=url, source="manual")
        with self._queue_lock:
            self._queue.append({"job_id": job_id, "type": "url", "url": url})
        logger.info("Enqueued URL job %s: %s", job_id, url)
        return job_id

    def enqueue_scan(self, source: str = "manual") -> str:
        """Add a full-site scan to the queue. Returns job_id."""
        job_id = StateManager.add_job(url=None, source=source)
        with self._queue_lock:
            self._queue.append({"job_id": job_id, "type": "scan"})
        logger.info("Enqueued scan job %s (source=%s)", job_id, source)
        return job_id

    # ── Status ────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        next_job = schedule.next_run()
        return {
            "running": self._thread is not None and self._thread.is_alive(),
            "next_run": str(next_job) if next_job else None,
            "queue_size": len(self._queue),
            "scan_times": Config.scan_times(),
        }

    # ── Main loop ─────────────────────────────────────────────────────────

    def _loop(self):
        while not self._stop_event.is_set():
            schedule.run_pending()

            with self._queue_lock:
                job = self._queue.pop(0) if self._queue else None

            if job:
                self._process_job(job)
            else:
                time.sleep(3)

    def _process_job(self, job: dict):
        from carousel_generator import generate_carousel
        from drive_uploader import upload_folder
        from output_manager import save_output
        from scraper import scrape_article, scrape_listing

        job_id = job["job_id"]
        StateManager.update_job(job_id, status="processing")

        try:
            if job["type"] == "url":
                stubs = [{"url": job["url"]}]
            else:
                # Scan listing page and filter already-processed URLs
                stubs = scrape_listing(Config.scan_url())
                processed = StateManager.get_processed_urls()
                stubs = [s for s in stubs if s["url"] not in processed]
                logger.info("Scan: %d new articles to process", len(stubs))

            results = []
            for stub in stubs:
                url = stub["url"]
                logger.info("Processing article: %s", url)

                article = scrape_article(url)
                if not article:
                    logger.warning("Skipping (scrape failed): %s", url)
                    continue

                carousel_data = generate_carousel(article)
                if not carousel_data:
                    logger.warning("Skipping (carousel gen failed): %s", url)
                    continue

                local_folder = save_output(carousel_data)
                drive_url = None
                if local_folder:
                    drive_url = upload_folder(local_folder, article["title"])

                StateManager.mark_processed(url)
                results.append({
                    "url": url,
                    "title": article["title"],
                    "drive_url": drive_url,
                    "local_folder": str(local_folder) if local_folder else None,
                })

            StateManager.update_job(job_id, status="done", results=results)
            logger.info("Job %s done — %d articles processed", job_id, len(results))

        except Exception as e:
            logger.exception("Job %s failed: %s", job_id, e)
            StateManager.update_job(job_id, status="error", error=str(e))


# ── Singleton accessor ────────────────────────────────────────────────────────

def get_worker() -> Worker:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = Worker()
    return _instance
