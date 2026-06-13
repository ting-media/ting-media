#!/usr/bin/env python
"""Generate secure keys for TING MEDIA."""

import secrets
from werkzeug.security import generate_password_hash

def main():
    # Generate strong secret key
    secret_key = secrets.token_hex(32)

    print("\n" + "=" * 70)
    print("TING MEDIA - Security Keys Generated")
    print("=" * 70)

    print(f"\nFLASK_SECRET_KEY (copy to .env):\n{secret_key}\n")

    # Default admin password
    default_password = "AMIT1144"
    admin_hash = generate_password_hash(default_password, method='pbkdf2:sha256')

    print(f"ADMIN_PASSWORD_HASH for '{default_password}':\n{admin_hash}\n")

    print("=" * 70)
    print("INSTRUCTIONS:")
    print("=" * 70)
    print("1. Open .env file")
    print("2. Replace FLASK_SECRET_KEY with the key above")
    print("3. Replace ADMIN_PASSWORD_HASH with the hash above")
    print("4. Run: python app_secure.py")
    print("=" * 70)
    print()

if __name__ == '__main__':
    main()
