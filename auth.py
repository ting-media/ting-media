"""
Secure authentication module with password hashing and session management.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

class AuthManager:
    """Manages authentication and session validation."""

    def __init__(self):
        self.max_attempts = int(os.getenv('MAX_LOGIN_ATTEMPTS', 5))
        self.attempt_window = int(os.getenv('LOGIN_ATTEMPT_WINDOW_MINUTES', 15))
        self.session_timeout = int(os.getenv('SESSION_TIMEOUT_MINUTES', 30))
        self.failed_attempts = {}  # In production, use Redis or database

    def _get_client_id(self):
        """Get client identifier (IP address)."""
        if request.environ.get('HTTP_X_FORWARDED_FOR'):
            return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0]
        return request.remote_addr

    def _check_rate_limit(self):
        """Check if client has exceeded login attempts."""
        if not os.getenv('RATE_LIMIT_ENABLED', 'True').lower() == 'true':
            return True

        client_id = self._get_client_id()
        now = datetime.now()

        if client_id in self.failed_attempts:
            attempts, first_attempt = self.failed_attempts[client_id]
            window_time = first_attempt + timedelta(minutes=self.attempt_window)

            if now < window_time:
                if attempts >= self.max_attempts:
                    logger.warning(f"Rate limit exceeded for IP: {client_id}")
                    return False
            else:
                # Window expired, reset
                del self.failed_attempts[client_id]
                return True

        return True

    def _record_failed_attempt(self):
        """Record failed login attempt."""
        client_id = self._get_client_id()
        now = datetime.now()

        if client_id in self.failed_attempts:
            attempts, first_attempt = self.failed_attempts[client_id]
            window_time = first_attempt + timedelta(minutes=self.attempt_window)

            if now < window_time:
                self.failed_attempts[client_id] = (attempts + 1, first_attempt)
            else:
                self.failed_attempts[client_id] = (1, now)
        else:
            self.failed_attempts[client_id] = (1, now)

    def _clear_attempts(self):
        """Clear failed attempts for client."""
        client_id = self._get_client_id()
        if client_id in self.failed_attempts:
            del self.failed_attempts[client_id]

    def validate_credentials(self, email, password):
        """
        Validate user credentials.
        Returns (success, user_data) tuple.
        """
        # Check rate limiting
        if not self._check_rate_limit():
            logger.warning(f"Login attempt blocked due to rate limiting for {email}")
            return False, {"error": "בדיקה של יותר מדי ניסיונות. נסה שוב בעוד 15 דקות"}

        # Validate credentials
        admin_email = os.getenv('ADMIN_EMAIL', 'amit@tingil.co')
        admin_password_hash = os.getenv('ADMIN_PASSWORD_HASH')

        if email == admin_email and admin_password_hash:
            if check_password_hash(admin_password_hash, password):
                self._clear_attempts()
                logger.info(f"Successful login for {email}")
                return True, {
                    "email": email,
                    "role": "admin",
                    "username": "אמית",
                    "login_time": datetime.now().isoformat()
                }

        # Failed login
        self._record_failed_attempt()
        logger.warning(f"Failed login attempt for {email}")
        return False, {"error": "אימייל או סיסמה שגויים"}

    def create_session(self, user_data):
        """Create secure session for authenticated user."""
        session.clear()
        session['user'] = {
            'email': user_data['email'],
            'role': user_data.get('role', 'user'),
            'username': user_data.get('username'),
            'login_time': user_data.get('login_time'),
            'created_at': datetime.now().isoformat()
        }
        session.permanent = True
        logger.info(f"Session created for {user_data['email']}")

    def is_authenticated(self):
        """Check if user has valid session."""
        if 'user' not in session:
            return False

        user = session['user']
        login_time = datetime.fromisoformat(user['created_at'])
        if datetime.now() - login_time > timedelta(minutes=self.session_timeout):
            session.clear()
            logger.info(f"Session expired for {user.get('email')}")
            return False

        return True

    def get_current_user(self):
        """Get current authenticated user."""
        if self.is_authenticated():
            return session.get('user')
        return None

    def logout(self):
        """Clear user session."""
        user_email = session.get('user', {}).get('email')
        session.clear()
        logger.info(f"Logout for {user_email}")


def require_auth(f):
    """Decorator to require authentication for endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = AuthManager()
        if not auth.is_authenticated():
            return jsonify({
                "error": "Unauthorized",
                "message": "חובה להתחבר למערכת"
            }), 401
        return f(*args, **kwargs)
    return decorated_function


def generate_password(password):
    """Generate bcrypt hash for password (for development/setup)."""
    return generate_password_hash(password, method='pbkdf2:sha256')
