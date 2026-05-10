"""
CMS Application for TING MEDIA - Complete backend with authentication and portfolio management.
Run with: python cms_app.py
Access at: http://localhost:5000
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_from_directory, session
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from auth import AuthManager, require_auth
from models import db, Portfolio, CarouselItem, ContentBlock, AdminUser

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG if os.getenv('DEBUG') == 'True' else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Create uploads directory
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'mp4', 'webm', 'avi', 'mov', 'jpg', 'jpeg', 'png', 'gif'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask app
app = Flask(__name__, static_folder='.', static_url_path='')
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', 'dev-key-change-in-production')
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
app.config['SESSION_COOKIE_HTTPONLY'] = os.getenv('SESSION_COOKIE_HTTPONLY', 'True').lower() == 'true'
app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
app.config['PERMANENT_SESSION_LIFETIME'] = 1800
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ting_media.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB for videos

# Initialize database
db.init_app(app)

# Initialize auth manager
auth_manager = AuthManager()

# ── SECURITY MIDDLEWARE ────────────────────────────────────────────────────────

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:5000,http://localhost:3000').split(',')
CORS(app, origins=[origin.strip() for origin in allowed_origins],
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     supports_credentials=True)

@app.before_request
def add_security_headers():
    request.security_headers = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',
        'X-XSS-Protection': '1; mode=block',
        'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
        'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; video-src 'self' data:",
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    }

@app.after_request
def apply_security_headers(response):
    for header, value in request.security_headers.items():
        response.headers[header] = value
    return response

# ── STATIC FILES & PAGES ───────────────────────────────────────────────────────

@app.route('/')
def root():
    try:
        return send_from_directory('.', 'index.html')
    except Exception as e:
        logger.error(f"Error serving index.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/login')
def login_page():
    try:
        return send_from_directory('.', 'login.html')
    except Exception as e:
        logger.error(f"Error serving login.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/dashboard')
def dashboard():
    if not auth_manager.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return send_from_directory('.', 'dashboard.html')
    except Exception as e:
        logger.error(f"Error serving dashboard.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/cms-admin')
def cms_admin():
    if not auth_manager.is_authenticated():
        return jsonify({"error": "Unauthorized"}), 401
    try:
        return send_from_directory('.', 'cms-admin.html')
    except Exception as e:
        logger.error(f"Error serving cms-admin.html: {e}")
        return "קובץ לא נמצא", 404

@app.route('/styles.css')
def styles():
    return send_from_directory('.', 'styles.css')

@app.route('/script.js')
def scripts():
    return send_from_directory('.', 'script.js')

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ── AUTHENTICATION API ─────────────────────────────────────────────────────────

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json() or {}
        email = data.get('email', '').strip()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({"error": "אימייל וסיסמה נדרשים"}), 400

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
    try:
        auth_manager.logout()
        return jsonify({"success": True, "message": "התנתקות בהצלחה"}), 200
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/auth/user', methods=['GET'])
def api_get_user():
    user = auth_manager.get_current_user()
    if user:
        return jsonify({"success": True, "user": {
            "email": user['email'],
            "username": user.get('username'),
            "role": user.get('role'),
        }}), 200
    return jsonify({"success": False, "user": None}), 200

@app.route('/api/auth/status', methods=['GET'])
def api_auth_status():
    return jsonify({"authenticated": auth_manager.is_authenticated()}), 200

# ── CMS API - PORTFOLIOS ───────────────────────────────────────────────────────

@app.route('/api/cms/portfolios', methods=['GET'])
def get_portfolios():
    try:
        portfolios = Portfolio.query.order_by(Portfolio.order).all()
        return jsonify({
            "success": True,
            "portfolios": [p.to_dict() for p in portfolios]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching portfolios: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/portfolios', methods=['POST'])
@require_auth
def create_portfolio():
    try:
        data = request.get_json() or {}

        portfolio = Portfolio(
            title=data.get('title'),
            description=data.get('description'),
            category=data.get('category'),
            video_url=data.get('video_url'),
            thumbnail_url=data.get('thumbnail_url'),
            duration=data.get('duration'),
            featured=data.get('featured', False),
            order=data.get('order', 0)
        )
        db.session.add(portfolio)
        db.session.commit()

        logger.info(f"Portfolio created: {portfolio.id}")
        return jsonify({
            "success": True,
            "message": "פרויקט נוצר בהצלחה",
            "portfolio": portfolio.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating portfolio: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/portfolios/<int:portfolio_id>', methods=['PUT'])
@require_auth
def update_portfolio(portfolio_id):
    try:
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            return jsonify({"error": "פרויקט לא נמצא"}), 404

        data = request.get_json() or {}
        portfolio.title = data.get('title', portfolio.title)
        portfolio.description = data.get('description', portfolio.description)
        portfolio.category = data.get('category', portfolio.category)
        portfolio.video_url = data.get('video_url', portfolio.video_url)
        portfolio.thumbnail_url = data.get('thumbnail_url', portfolio.thumbnail_url)
        portfolio.duration = data.get('duration', portfolio.duration)
        portfolio.featured = data.get('featured', portfolio.featured)
        portfolio.order = data.get('order', portfolio.order)
        portfolio.updated_at = datetime.utcnow()

        db.session.commit()
        logger.info(f"Portfolio updated: {portfolio_id}")
        return jsonify({
            "success": True,
            "message": "פרויקט עודכן בהצלחה",
            "portfolio": portfolio.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating portfolio: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/portfolios/<int:portfolio_id>', methods=['DELETE'])
@require_auth
def delete_portfolio(portfolio_id):
    try:
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            return jsonify({"error": "פרויקט לא נמצא"}), 404

        db.session.delete(portfolio)
        db.session.commit()
        logger.info(f"Portfolio deleted: {portfolio_id}")
        return jsonify({"success": True, "message": "פרויקט מחוק בהצלחה"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting portfolio: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

# ── CMS API - CAROUSEL ───────────────────────────────────────────────────────

@app.route('/api/cms/carousel', methods=['GET'])
def get_carousel():
    try:
        items = CarouselItem.query.filter_by(active=True).order_by(CarouselItem.order).all()
        return jsonify({
            "success": True,
            "carousel": [item.to_dict() for item in items]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching carousel: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/carousel', methods=['POST'])
@require_auth
def create_carousel_item():
    try:
        data = request.get_json() or {}
        item = CarouselItem(
            title=data.get('title'),
            description=data.get('description'),
            image_url=data.get('image_url'),
            video_url=data.get('video_url'),
            order=data.get('order', 0),
            active=True
        )
        db.session.add(item)
        db.session.commit()
        logger.info(f"Carousel item created: {item.id}")
        return jsonify({
            "success": True,
            "message": "פריט נוסף בהצלחה",
            "item": item.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating carousel item: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/carousel/<int:item_id>', methods=['DELETE'])
@require_auth
def delete_carousel_item(item_id):
    try:
        item = CarouselItem.query.get(item_id)
        if not item:
            return jsonify({"error": "פריט לא נמצא"}), 404

        db.session.delete(item)
        db.session.commit()
        logger.info(f"Carousel item deleted: {item_id}")
        return jsonify({"success": True, "message": "פריט מחוק בהצלחה"}), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting carousel item: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

# ── CMS API - CONTENT BLOCKS ───────────────────────────────────────────────────

@app.route('/api/cms/content', methods=['GET'])
def get_content():
    try:
        blocks = ContentBlock.query.order_by(ContentBlock.order).all()
        return jsonify({
            "success": True,
            "content": [block.to_dict() for block in blocks]
        }), 200
    except Exception as e:
        logger.error(f"Error fetching content: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/content/<section_name>', methods=['GET'])
def get_content_section(section_name):
    try:
        block = ContentBlock.query.filter_by(section_name=section_name).first()
        if not block:
            return jsonify({"error": "סעיף לא נמצא"}), 404
        return jsonify({"success": True, "content": block.to_dict()}), 200
    except Exception as e:
        logger.error(f"Error fetching content section: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

@app.route('/api/cms/content/<section_name>', methods=['PUT'])
@require_auth
def update_content_section(section_name):
    try:
        block = ContentBlock.query.filter_by(section_name=section_name).first()
        if not block:
            block = ContentBlock(section_name=section_name)
            db.session.add(block)

        data = request.get_json() or {}
        block.title = data.get('title', block.title)
        block.description = data.get('description', block.description)
        block.subtitle = data.get('subtitle', block.subtitle)
        block.button_text = data.get('button_text', block.button_text)
        block.button_link = data.get('button_link', block.button_link)
        block.updated_at = datetime.utcnow()

        db.session.commit()
        logger.info(f"Content section updated: {section_name}")
        return jsonify({
            "success": True,
            "message": "תוכן עודכן בהצלחה",
            "content": block.to_dict()
        }), 200
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating content section: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

# ── CMS API - FILE UPLOAD ──────────────────────────────────────────────────────

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/cms/upload', methods=['POST'])
@require_auth
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "קובץ לא צורף"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "קובץ לא נבחר"}), 400

        if not allowed_file(file.filename):
            return jsonify({"error": "סוג קובץ לא מותר"}), 400

        filename = secure_filename(f"{datetime.utcnow().timestamp()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        logger.info(f"File uploaded: {filename}")
        return jsonify({
            "success": True,
            "message": "קובץ העלה בהצלחה",
            "file_url": f"/uploads/{filename}",
            "filename": filename
        }), 201
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        return jsonify({"error": "שגיאה בשרת"}), 500

# ── ERROR HANDLERS ─────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(error):
    logger.warning(f"404 Not Found: {request.path}")
    return jsonify({"error": "דף לא נמצא"}), 404

@app.errorhandler(500)
def server_error(error):
    logger.error(f"500 Server Error: {error}")
    return jsonify({"error": "שגיאה בשרת"}), 500

# ── INITIALIZE DATABASE ────────────────────────────────────────────────────────

def init_database():
    with app.app_context():
        db.create_all()

        # Create default admin user if not exists
        admin = AdminUser.query.filter_by(email='amit@tingil.co').first()
        if not admin:
            admin = AdminUser(
                email='amit@tingil.co',
                name='אמית',
                role='admin'
            )
            admin.set_password('AMIT1144')
            db.session.add(admin)
            db.session.commit()
            logger.info("Admin user created")

        # Create sample portfolios if empty
        if Portfolio.query.count() == 0:
            sample_portfolios = [
                Portfolio(title='Commercial - Bank', category='Commercial',
                         description='פרסומת בנק ישראלית',
                         video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=1),
                Portfolio(title='Social Media Reel', category='Social Media',
                         description='תוכן לאינסטגרם',
                         video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=2),
                Portfolio(title='Event Coverage', category='Event',
                         description='סרט אירוע עסקי',
                         video_url='https://www.youtube.com/watch?v=dQw4w9WgXcQ', order=3),
            ]
            db.session.add_all(sample_portfolios)
            db.session.commit()
            logger.info("Sample portfolios created")

# ── START SERVER ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_database()
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    logger.info(f"Starting TING MEDIA CMS server on port {port}")
    logger.info(f"Debug mode: {debug}")
    app.run(host='0.0.0.0', port=port, debug=debug)
