"""The 2FA QR code must work when Pillow is NOT installed (the production container only has qrcode + pypng).
Run from the repo root:  python tests/test_qr_without_pillow.py"""
import base64, os, sys, tempfile

sys.modules["PIL"] = None            # pretend Pillow is missing: qrcode then uses its pure-Python PNG writer
os.environ.update(DATABASE_URL=f"sqlite:///{tempfile.mkdtemp()}/q.db", SECRET_KEY="k" * 40, FLASK_ENV="development")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app_db
from models import User

with app_db.app.app_context():
    u = User(username="q", email="q@x.io", password_hash="x")
    u.enable_totp()
    png = base64.b64decode(u.get_totp_qr_code())
    assert png[:8] == b"\x89PNG\r\n\x1a\n", png[:8]
    assert len(png) > 500
print("ok QR code renders without Pillow")
