"""Importing app_db (as gunicorn does) must upgrade an old database by itself, with no init_db() call.
Run from the repo root:  python tests/test_gunicorn_import.py"""
import os, sqlite3, sys, tempfile

tmp = tempfile.mkdtemp(); path = f"{tmp}/old.db"
con = sqlite3.connect(path)
con.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY, username VARCHAR(80), email VARCHAR(120), password_hash VARCHAR(255),
 role VARCHAR(20), is_active BOOLEAN, is_2fa_enabled BOOLEAN, totp_secret VARCHAR(32), backup_codes JSON, oauth_providers JSON,
 last_login DATETIME, last_ip VARCHAR(45), login_attempts INTEGER, locked_until DATETIME, created_at DATETIME, updated_at DATETIME);""")
con.commit(); con.close()
os.environ.update(DATABASE_URL=f"sqlite:///{path}", SECRET_KEY="k" * 40, FLASK_ENV="development")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app_db                                   # no init_db(): this is what gunicorn does
from models import User, db
from werkzeug.security import generate_password_hash

with app_db.app.app_context():
    db.session.add(User(username="Elijah", email="e@x.io", password_hash=generate_password_hash("a-long-password-1"), role="admin", is_active=True))
    db.session.commit()
    app_db.ensure_schema()                       # a second worker doing the same must be harmless

c = app_db.app.test_client()
import re
tok = re.search(r'name="csrf_token" value="([^"]+)"', c.get("/login").get_data(as_text=True)).group(1)
r = c.post("/login", data={"username": "Elijah", "password": "a-long-password-1", "csrf_token": tok})
assert r.status_code == 302 and r.headers["Location"].endswith("/dashboard"), (r.status_code, r.headers.get("Location"))
print("ok old database upgraded on import, login works")
