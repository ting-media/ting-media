# 🔐 TING MEDIA - Security Setup Guide

## Overview
This guide explains how to set up the secure authentication system for TING MEDIA.

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Generate Admin Password Hash
```bash
python
>>> from auth import generate_password
>>> password_hash = generate_password('your-secure-password-here')
>>> print(password_hash)
```

### 3. Update .env File
Edit `.env` and replace:
- `ADMIN_PASSWORD_HASH` with the hash from step 2
- `FLASK_SECRET_KEY` with a strong random key (min 32 chars)

**To generate a strong secret key:**
```bash
python
>>> import secrets
>>> print(secrets.token_hex(32))
```

### 4. Run Secure Server
```bash
python app_secure.py
```

Server runs on: `http://localhost:5000`

---

## 📋 Configuration Options

### Environment Variables (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `FLASK_ENV` | development | Flask environment |
| `FLASK_SECRET_KEY` | Required | Session encryption key (32+ chars) |
| `DEBUG` | False | Debug mode (never True in production) |
| `ADMIN_EMAIL` | amit@tingil.co | Admin email |
| `ADMIN_PASSWORD_HASH` | Required | Bcrypt hash of password |
| `SESSION_TIMEOUT_MINUTES` | 30 | Session expiration time |
| `SESSION_COOKIE_SECURE` | False | HTTPS only (True in production) |
| `SESSION_COOKIE_HTTPONLY` | True | No JavaScript access to cookies |
| `SESSION_COOKIE_SAMESITE` | Lax | CSRF protection level |
| `ALLOWED_ORIGINS` | localhost | CORS origins (comma-separated) |
| `MAX_LOGIN_ATTEMPTS` | 5 | Failed login attempts before lockout |
| `LOGIN_ATTEMPT_WINDOW_MINUTES` | 15 | Lockout window |
| `RATE_LIMIT_ENABLED` | True | Enable rate limiting |
| `LOG_LEVEL` | INFO | Logging level |
| `LOG_FILE` | logs/auth.log | Log file path |

---

## 🔒 Security Features

### Implemented

✅ **Password Hashing**
- Uses werkzeug's PBKDF2:SHA256 hashing
- Never store plaintext passwords

✅ **Session Management**
- Server-side sessions with Flask sessions
- HTTP-only cookies (no JavaScript access)
- Automatic timeout (configurable)
- Session validation on every request

✅ **Rate Limiting**
- Blocks after N failed login attempts
- IP-based tracking
- Configurable attempt window

✅ **Security Headers**
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (HTTPS)
- `Content-Security-Policy`
- `Referrer-Policy: strict-origin-when-cross-origin`

✅ **CORS Protection**
- Configurable allowed origins
- Credentials required for cross-origin requests

✅ **Logging & Monitoring**
- All authentication events logged
- IP addresses tracked for rate limiting
- Session events recorded

### Todo for Production

⏳ **Database Backend**
- Move credentials from environment to secure database
- Use bcrypt or argon2 for password hashing
- Implement user management

⏳ **HTTPS/TLS**
- Enable `SESSION_COOKIE_SECURE=True`
- Obtain SSL certificate
- Force HTTPS redirect

⏳ **Two-Factor Authentication**
- TOTP implementation
- Backup codes

⏳ **Advanced Logging**
- Centralized log aggregation
- Error tracking (e.g., Sentry)
- Monitoring alerts

---

## 🧪 Testing

### Manual Login Testing
1. Open `http://localhost:5000/login`
2. Use credentials from `.env` (ADMIN_EMAIL / password you set)
3. Should redirect to `/dashboard`

### Session Testing
```bash
curl -b cookies.txt -c cookies.txt -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"amit@tingil.co","password":"YOUR_PASSWORD"}'

# Check session
curl -b cookies.txt http://localhost:5000/api/auth/user
```

### Rate Limiting Test
```bash
# Try 5 incorrect logins with same IP
for i in {1..6}; do
  curl -X POST http://localhost:5000/api/auth/login \
    -H "Content-Type: application/json" \
    -d '{"email":"amit@tingil.co","password":"wrong"}'
  echo "Attempt $i"
done
# 6th attempt should be blocked
```

---

## 📁 File Structure

```
├── app_secure.py           # Main Flask app with auth
├── auth.py                 # Authentication module
├── login.html              # Login page (no hardcoded credentials)
├── dashboard.html          # Protected dashboard (uses API)
├── .env                    # Environment configuration (NEVER COMMIT)
├── .gitignore              # Git ignore rules (protects secrets)
├── requirements.txt        # Python dependencies
└── SETUP_SECURITY.md       # This file
```

---

## 🚨 Common Issues

### "אימייל או סיסמה שגויים" (Wrong credentials error)
- Check ADMIN_EMAIL in .env
- Verify password hash was set correctly
- Check browser console for actual error

### Session expires immediately
- Check SESSION_TIMEOUT_MINUTES in .env
- Ensure FLASK_SECRET_KEY is set
- Check cookie settings

### Rate limiting blocks too early
- Increase MAX_LOGIN_ATTEMPTS in .env
- Increase LOGIN_ATTEMPT_WINDOW_MINUTES
- Or disable with RATE_LIMIT_ENABLED=False (dev only)

### CORS errors
- Add your origin to ALLOWED_ORIGINS in .env
- Separate multiple origins with commas

---

## 🔄 Deployment Checklist

Before going to production:

- [ ] Change `FLASK_ENV` to `production`
- [ ] Set `DEBUG` to `False`
- [ ] Generate strong `FLASK_SECRET_KEY`
- [ ] Change admin password and regenerate hash
- [ ] Enable `SESSION_COOKIE_SECURE=True` (requires HTTPS)
- [ ] Set up HTTPS/SSL certificate
- [ ] Configure ALLOWED_ORIGINS with production domain
- [ ] Set up centralized logging
- [ ] Enable security headers in production
- [ ] Set up monitoring/alerting
- [ ] Review and rotate credentials regularly
- [ ] Implement database backend instead of environment variables
- [ ] Add two-factor authentication
- [ ] Set up automated backups

---

## 📚 Additional Resources

- [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
- [Flask Security](https://flask.palletsprojects.com/en/3.0.x/security/)
- [werkzeug Security Functions](https://werkzeug.palletsprojects.com/en/3.0.x/security/)

---

**Last Updated:** May 2026
**Security Level:** Development Ready (⚠️ Needs production hardening)
