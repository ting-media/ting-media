"""
Secure Flask web server for TING MEDIA with authentication.
Run with: python app_secure.py
Access at: http://localhost:5000
"""

import os
import logging
from datetime import datetime
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

from auth import AuthManager, require_auth, generate_password

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.getLogger().DEBUG if os.getenv('DEBUG') == 'True' else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = os.getenv('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes

# Initialize auth manager
auth_manager = AuthManager()

# ── SECURITY MIDDLEWARE ────────────────────────────────────────────────────────

# Trust proxy headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

# CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5000,http://localhost:3000').split(',')
CORS(app, origins=[origin.strip() for origin in allowed_origins],
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'OPTIONS'],
     supports_credentials=True)

@app.before_request
def add_security_headers():
    """Add security headers to all responses."""
    request.security_headers = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:",
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }

@app.after_request
def apply_security_headers(response):
    """Apply security headers to response."""
    for header, value in request.security_headers.items():
        response.headers[header] = value
    return response

# ── STATIC FILES & PAGES ───────────────────────────────────────────────────────

@app.route('/')
def root():
    """Serve index.html (public landing page)."""
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/styles.css')
def styles():
    """Serve CSS file."""
    return send_from_directory('.', 'styles.css')

@app.route('/script.js')
def scripts():
    """Serve JavaScript file."""
    return send_from_directory('.', 'script.js')

@app.route('/login')
def login_page():
    """Serve login page."""
    try:
        return send_from_directory('.', 'login.html')
    except Exception as e:
        logger.error(f"Error serving login.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/dashboard')
def dashboard():
    """Serve dashboard (protected)."""
    if not auth_manager.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return send_from_directory('.', 'dashboard.html')
    except Exception as e:
        logger.error(f"Error serving dashboard.html: {e}")
        return "קובץ לא נמצא", 404

# ── AUTHENTICATION API ─────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    """
    Login endpoint - validate credentials and create session.
    POST /api/auth/login
    Body: {"email": "...", "password": "..."}
    """
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            logger.warning("Login attempt with missing credentials")
            return jsonify({"error": "אימייל וסיסמה נדרשים"}), 400

        # Validate credentials
        success, user_data = auth_manager.validate_credentials(email, password)

        if success:
            auth_manager.create_session(user_data)
            return jsonify({
                "success": True,
                "message": "התחברות בהצלחה",
                "user": {
                    "email": user_data['email'],
                    "username": user_data.get('username'),
                    "role": user_data.get('role')
                }
            }), 200

        return jsonify(user_data), 401

    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def api_logout():
    """
    Logout endpoint - clear session.
    POST /api/auth/logout
    """
    try:
        auth_manager.logout()
        return jsonify({
            "success": True,
            "message": "התנתקות בהצלחה"
        }), 200
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/auth/user', methods=['GET'])
def api_get_user():
    """
    Get current user info.
    GET /api/auth/user
    """
    user = auth_manager.get_current_user()
    if user:
        return jsonify({
            "success": True,
            "user": {
                "email": user['email'],
                "username": user.get('username'),
                "role": user.get('role'),
                "login_time": user.get('login_time')
            }
        }), 200
    return jsonify({"success": False, "user": None}), 200

@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    """Check if user is authenticated."""
    return jsonify({
        "authenticated": auth_manager.is_authenticated()
    }), 200

# ── ADMIN ENDPOINTS ────────────────────────────────────────────────────────────

@app.route('/api/admin/dashboard', methods=['GET'])
@require_auth
def api_dashboard():
    """Get dashboard data (protected)."""
    user = auth_manager.get_current_user()
    return jsonify({
        "success": True,
        "dashboard": {
            "title": "לוח בקרה",
            "user": user.get('username'),
            "role": user.get('role'),
            "timestamp": datetime.now().isoformat()
        }
    }), 200

# ── ERROR HANDLERS ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "דף לא נמצא"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"500 Server Error: {error}")
    return jsonify({"error": "שגיאה בשרת"}), 500

@app.errorhandler(403)
def forbidden(error):
    logger.warning(f"403 Forbidden: {request.path}")
    return jsonify({"error": "גישה נדחית"}), 403

# ── UTILITY ────────────────────────────────────────────────────────────────────

@app.cli.command()
def generate_admin_password():
    """CLI command to generate password hash for admin."""
    password = input("הזן סיסמה חדשה: ")
    hashed = generate_password(password)
    print(f"\nהעתק את ערך זה לקובץ .env בשדה ADMIN_PASSWORD_HASH:")
    print(hashed)

# ── START SERVER ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    logger.info(f"Starting TING MEDIA secure server on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Allowed origins: {', '.join(allowed_origins)}")
    app.run(host='0.0.0.0', port=port, debug=debug)
