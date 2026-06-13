"""
Main entry point - Scheduler + Flask app
"""
import sys
from pathlib import Path
from datetime import datetime
import json

from flask import Flask, render_template, jsonify, request, send_file
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import atexit

from agent import WhatsAppGmailAgent
from state_manager import StateManager
from config import (
    FLASK_HOST, FLASK_PORT, SCHEDULER_INTERVAL_MINUTES,
    TEMPLATES_DIR, STATIC_DIR, STATE_DIR, DEBUG
)

# Initialize Flask
app = Flask(__name__, template_folder=str(TEMPLATES_DIR), static_folder=str(STATIC_DIR))
app.config['JSON_SORT_KEYS'] = False

# Initialize agent and state manager
agent = WhatsAppGmailAgent()
state_manager = StateManager()

# Global state
sync_history = []
last_sync = None

# ============================================================================
# SCHEDULER
# ============================================================================

scheduler = BackgroundScheduler()

def scheduled_sync():
    """Run sync job"""
    global last_sync, sync_history

    try:
        print(f"\n⏰ Scheduled sync at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        result = agent.run_sync(hours=1)

        last_sync = result
        sync_history.append(result)

        # Keep only last 100 syncs
        sync_history = sync_history[-100:]

        # Save to file for persistence
        with open(STATE_DIR / "sync_history.json", "w", encoding="utf-8") as f:
            json.dump(sync_history, f, ensure_ascii=False, indent=2)

    except Exception as e:
        print(f"❌ Sync error: {e}")
        import traceback
        traceback.print_exc()

def start_scheduler():
    """Start background scheduler"""
    try:
        scheduler.add_job(
            scheduled_sync,
            trigger=IntervalTrigger(minutes=SCHEDULER_INTERVAL_MINUTES),
            id='whatsapp_gmail_sync',
            name='WhatsApp + Gmail Sync',
            replace_existing=True,
            max_instances=1
        )

        scheduler.start()
        print(f"✓ Scheduler started (every {SCHEDULER_INTERVAL_MINUTES} minutes)")

    except Exception as e:
        print(f"Error starting scheduler: {e}")

def stop_scheduler():
    """Stop scheduler"""
    scheduler.shutdown(wait=False)

atexit.register(stop_scheduler)

# ============================================================================
# FLASK ROUTES
# ============================================================================

@app.route('/')
def dashboard():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/dashboard-data')
def api_dashboard_data():
    """Get dashboard data"""
    data = agent.get_dashboard_data()
    return jsonify(data)

@app.route('/api/tasks')
def api_tasks():
    """Get all tasks"""
    tasks = state_manager.get_open_tasks()
    return jsonify({'tasks': tasks})

@app.route('/api/messages')
def api_messages():
    """Get recent messages"""
    hours = request.args.get('hours', 24, type=int)
    messages = state_manager.get_recent_messages(hours=hours)
    return jsonify({'messages': messages})

@app.route('/api/analytics')
def api_analytics():
    """Get analytics"""
    hours = request.args.get('hours', 24, type=int)
    analytics = state_manager.get_analytics(hours=hours)
    return jsonify(analytics)

@app.route('/api/sync-history')
def api_sync_history():
    """Get sync history"""
    return jsonify({'syncs': sync_history[-20:]})  # Last 20

@app.route('/api/sync-now', methods=['POST'])
def api_sync_now():
    """Trigger sync immediately"""
    try:
        result = agent.run_sync(hours=1)
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/task/<task_id>/status', methods=['PUT'])
def api_update_task_status(task_id):
    """Update task status"""
    try:
        data = request.get_json()
        new_status = data.get('status')

        if new_status not in ['open', 'in_progress', 'completed']:
            return jsonify({'error': 'Invalid status'}), 400

        state_manager.update_task_status(task_id, new_status)
        return jsonify({'status': 'success'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/summary')
def api_export_summary():
    """Export hourly summary"""
    if last_sync:
        filename = f"summary_{last_sync['timestamp'].replace(':', '-')}.json"
        return jsonify(last_sync)
    return jsonify({'error': 'No sync data'}), 404

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({'error': str(error)}), 500

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='WhatsApp + Gmail Agent')
    parser.add_argument('--no-scheduler', action='store_true', help='Disable scheduler')
    parser.add_argument('--test-sync', action='store_true', help='Run one sync and exit')
    parser.add_argument('--port', type=int, default=FLASK_PORT, help='Flask port')
    parser.add_argument('--host', default=FLASK_HOST, help='Flask host')

    args = parser.parse_args()

    print("\n" + "="*60)
    print("🤖 WhatsApp + Gmail Agent")
    print("="*60 + "\n")

    # Run test sync if requested
    if args.test_sync:
        print("Running test sync...\n")
        result = agent.run_sync(hours=1)
        print("\nTest sync completed successfully!")
        print(f"Summary: {result['summary'][:200]}...")
        return

    # Start scheduler if enabled
    if not args.no_scheduler:
        start_scheduler()
        print(f"📊 Dashboard: http://{args.host}:{args.port}\n")
    else:
        print("⚠️  Scheduler disabled\n")

    # Start Flask
    try:
        print(f"Starting Flask on {args.host}:{args.port}...")
        app.run(
            host=args.host,
            port=args.port,
            debug=DEBUG,
            use_reloader=False
        )
    except KeyboardInterrupt:
        print("\n\nShutting down...")
    finally:
        agent.close()

if __name__ == '__main__':
    main()
