"""
Flask web UI for the carousel automation tool.
Run with: python app.py
Access at: http://localhost:5000
"""

import logging

from flask import Flask, jsonify, render_template, request

from config import Config
from state_manager import StateManager
from worker import get_worker

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── App init ──────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "carousel-tool-secret-key"

# Start background worker
worker = get_worker()
worker.start()


# ── Pages ─────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    jobs = StateManager.get_jobs(limit=30)
    status = worker.get_status()
    return render_template("index.html", jobs=jobs, status=status)


@app.route("/settings", methods=["GET", "POST"])
def settings():
    saved = False
    if request.method == "POST":
        scan_url = request.form.get("scan_url", "").strip()
        scan_times = [
            t.strip()
            for t in request.form.getlist("scan_times")
            if t.strip()
        ]
        anthropic_key = request.form.get("anthropic_api_key", "").strip()
        drive_key_path = request.form.get("google_service_account_key_path", "").strip()
        drive_folder_id = request.form.get("google_drive_root_folder_id", "").strip()
        output_dir = request.form.get("output_dir", "").strip()

        if not scan_times:
            scan_times = ["07:00"]

        updates = {
            "SCAN_URL": scan_url or Config.scan_url(),
            "SCAN_TIMES": ",".join(scan_times),
        }
        if anthropic_key:
            updates["ANTHROPIC_API_KEY"] = anthropic_key
        if drive_key_path:
            updates["GOOGLE_SERVICE_ACCOUNT_KEY_PATH"] = drive_key_path
        if drive_folder_id:
            updates["GOOGLE_DRIVE_ROOT_FOLDER_ID"] = drive_folder_id
        if output_dir:
            updates["OUTPUT_DIR"] = output_dir

        for key, value in updates.items():
            Config.set(key, value)

        worker.refresh_schedule()
        saved = True

    return render_template("settings.html", config=Config, saved=saved)


# ── API endpoints ─────────────────────────────────────────────────────────────

@app.route("/api/scan", methods=["POST"])
def api_scan():
    job_id = worker.enqueue_scan(source="manual")
    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/api/process", methods=["POST"])
def api_process():
    data = request.get_json(silent=True) or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400
    job_id = worker.enqueue_url(url)
    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/api/jobs")
def api_jobs():
    limit = request.args.get("limit", 50, type=int)
    return jsonify(StateManager.get_jobs(limit=limit))


@app.route("/api/job/<job_id>")
def api_job(job_id):
    job = StateManager.get_job(job_id)
    if not job:
        return jsonify({"error": "Not found"}), 404
    return jsonify(job)


@app.route("/api/status")
def api_status():
    return jsonify(worker.get_status())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
