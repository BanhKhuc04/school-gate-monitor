"""
Quick script to reset a user's password.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_user_by_username, update_user
from app.auth import hash_password

if len(sys.argv) != 3:
    print("Usage: python reset_pw.py <username> <new_password>")
    sys.exit(1)

username = sys.argv[1]
new_password = sys.argv[2]

user = get_user_by_username(username)
if not user:
    print(f"ERROR: User '{username}' not found")
    sys.exit(1)

pw_hash = hash_password(new_password)
success = update_user(user['id'], password_hash=pw_hash)
if success:
    print(f"OK: Password for '{username}' has been reset")
else:
    print(f"ERROR: Failed to update password")
    sys.exit(1)
