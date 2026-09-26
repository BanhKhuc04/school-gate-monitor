"""
CLI script to seed a user into the database.
Usage:
    python scripts/seed_user.py --username admin --password secret123 --role admin
    python scripts/seed_user.py -u guard01 -p guardpass -r security
    python scripts/seed_user.py -u principal01 -p mgmtpass -r management
"""
import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import create_user, get_user_by_username, init_db
from app.auth import hash_password


VALID_ROLES = {"admin", "security", "management"}


def main():
    parser = argparse.ArgumentParser(description="Seed a user into the database")
    parser.add_argument("--username", "-u", required=True, help="Username")
    parser.add_argument("--password", "-p", required=True, help="Password")
    parser.add_argument(
        "--role", "-r", required=True,
        choices=list(VALID_ROLES),
        help="Role: admin, security, or management"
    )
    args = parser.parse_args()

    # Ensure DB exists
    init_db()

    # Check if user already exists
    existing = get_user_by_username(args.username)
    if existing:
        print(f"ERROR: Username '{args.username}' already exists (role: {existing['role']})")
        sys.exit(1)

    # Hash password and create user
    pw_hash = hash_password(args.password)
    user_id = create_user(args.username, pw_hash, args.role)
    print(f"OK: Created user '{args.username}' with role '{args.role}' (id={user_id})")


if __name__ == "__main__":
    main()
