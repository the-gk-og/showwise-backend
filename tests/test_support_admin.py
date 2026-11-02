"""Run from the repo root:  python tests/test_support_admin.py"""
import base64, json, os, re, sys, tempfile
from urllib.parse import parse_qs, urlparse

tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/test.db"
os.environ["SUPPORT_MASTER_KEY"] = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyotp
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

import app_db
from models import Log, Organization, Setting, SupportSigningKey, User, db
from support_admin import public_keys_env

app = app_db.app
app.config["TESTING"] = True
app_db.init_db()
with app.app_context():
    admin = User.query.filter_by(username="admin").first()
    secret, _ = admin.enable_totp(); admin.is_2fa_enabled = True
    db.session.add(User(username="bob", email="bob@x.io", password_hash="x", role="user", is_active=True))
    org = Organization.query.filter_by(slug="demo").first()
    db.session.add(Organization(name="Greenroom", slug="greenroom", url="https://crew.greenroom.org"))
    db.session.add(Organization(name="Plain HTTP", slug="plainhttp", url="http://insecure.example.com"))
    db.session.commit()
    ADMIN_ID, BOB_ID = admin.id, User.query.filter_by(username="bob").first().id


def client(uid=ADMIN_ID, role="admin", name="admin"):
    c = app.test_client()
    with c.session_transaction() as s:
        s["user_id"], s["role"], s["username"] = uid, role, name
    return c


def csrf(c, path="/support/org/greenroom"):
    return re.search(r'name="csrf_token" value="([^"]+)"', c.get(path).get_data(as_text=True)).group(1)


def mint(c, slug="greenroom", **kw):
    data = {"csrf_token": csrf(c, f"/support/org/{slug}"), "scope": "readonly", "minutes": "10",
            "reason": "ticket 42", "totp": pyotp.TOTP(secret).now(), **kw}
    return c.post(f"/support/org/{slug}/login", data=data)


def verify(token, aud):
    pad = lambda s: s + "=" * (-len(s) % 4)
    p, sig = token.split(".")
    pb, sg = base64.urlsafe_b64decode(pad(p)), base64.urlsafe_b64decode(pad(sig))
    with app.app_context():
        keys = public_keys_env().split(",")
    for k in keys:
        try:
            Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(pad(k))).verify(sg, pb)
            d = json.loads(pb); assert d["aud"] == aud and d["iss"] == "showwise-support"
            return d
        except InvalidSignature:
            pass


def test_access_control():
    assert app.test_client().get("/support/").status_code == 302                       # anonymous -> login
    assert client(BOB_ID, "user", "bob").get("/support/").status_code == 403           # non-admin
    assert client(BOB_ID, "user", "bob").post("/support/keys/rotate").status_code in (400, 403)


def test_index_creates_key_and_lists_orgs():
    r = client().get("/support/"); html = r.get_data(as_text=True)
    assert r.status_code == 200 and "greenroom" in html and "demo" in html
    with app.app_context():
        assert SupportSigningKey.query.filter_by(status="active").count() == 1
    assert 'Support' in client().get("/dashboard").get_data(as_text=True)               # nav link


def test_mint_flow():
    c = client(); r = mint(c)
    assert r.status_code == 303 and r.headers["Referrer-Policy"] == "no-referrer"
    u = urlparse(r.headers["Location"])
    assert f"{u.scheme}://{u.netloc}{u.path}" == "https://crew.greenroom.org/support/login"
    d = verify(parse_qs(u.query)["token"][0], "greenroom")
    assert d and d["sub"] == "admin" and d["scope"] == "readonly" and d["exp"] - d["iat"] == 600
    with app.app_context():
        row = Log.query.filter_by(log_type="support_login").order_by(Log.id.desc()).first()
        assert "greenroom" in row.message and "ticket 42" in row.message and row.event_metadata["jti"] == d["jti"]


def test_guards():
    c = client(); url = "/support/org/greenroom/login"
    assert c.post(url, data={"scope": "readonly"}).status_code == 400                  # CSRF enforced by app
    assert mint(c, totp="000000").status_code == 302                                   # bad 2FA
    for bad in ({"scope": "root"}, {"minutes": "999"}, {"reason": ""}):
        assert mint(c, **bad).status_code == 302
    assert mint(c, "plainhttp").status_code == 302                                     # http:// URL refused
    with app.app_context():
        assert Log.query.filter(Log.log_type == "support_denied").count() >= 1
        assert User.query.get(ADMIN_ID).login_attempts >= 1                            # shared lockout counter


def test_requires_2fa_on_account():
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.is_2fa_enabled = False; db.session.commit()
    try:
        assert mint(client()).status_code == 302
        assert "Turn on 2FA" in client().get("/support/org/greenroom").get_data(as_text=True)
    finally:
        with app.app_context():
            u = User.query.get(ADMIN_ID); u.is_2fa_enabled = True; u.login_attempts = 0; db.session.commit()


def test_2fa_setup_page_and_api_csrf_header():
    c = client(); r = c.get("/support/2fa")
    assert r.status_code == 200 and "Two-factor authentication" in r.get_data(as_text=True)
    page = r.get_data(as_text=True)
    token = re.search(r'const csrf = "([^"]+)"', page).group(1)
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.is_2fa_enabled = False; db.session.commit()
    try:
        d = c.get("/api/user/2fa/setup").get_json()                                       # existing endpoint
        ok = c.post("/api/user/2fa/verify", json={"token": pyotp.TOTP(d["secret"]).now()},
                    headers={"X-CSRFToken": token})                                       # what the page sends
        assert ok.status_code == 200 and ok.get_json()["success"]
    finally:
        with app.app_context():
            u = User.query.get(ADMIN_ID); u.totp_secret = secret; u.is_2fa_enabled = True; db.session.commit()


def test_per_org_disable():
    c = client(); c.post("/support/org/greenroom/toggle", data={"csrf_token": csrf(c)})
    assert mint(c).status_code == 302
    c.post("/support/org/greenroom/toggle", data={"csrf_token": csrf(c)})
    assert mint(c).status_code == 303


def test_rotation_and_revoke():
    c = client()
    with app.app_context():
        old = public_keys_env()
    c.post("/support/keys/rotate", data={"csrf_token": csrf(c)})
    with app.app_context():
        env = public_keys_env()
    new, prev = env.split(",")
    assert prev == old and new != old
    tok = parse_qs(urlparse(mint(c).headers["Location"]).query)["token"][0]
    assert verify(tok, "greenroom")
    kid = re.findall(r"/keys/(\w+)/revoke", c.get("/support/").get_data(as_text=True))[0]
    c.post(f"/support/keys/{kid}/revoke", data={"csrf_token": csrf(c)})
    with app.app_context():
        assert public_keys_env() == new


def test_private_key_encrypted_and_master_key_checked():
    with app.app_context():
        assert SupportSigningKey.query.filter_by(status="active").first().private_enc.startswith("gAAAA")
    good = os.environ["SUPPORT_MASTER_KEY"]
    os.environ["SUPPORT_MASTER_KEY"] = __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
    try:
        assert mint(client()).status_code == 500
    finally:
        os.environ["SUPPORT_MASTER_KEY"] = good
    del os.environ["SUPPORT_MASTER_KEY"]
    try:
        assert client().get("/support/").status_code == 503
    finally:
        os.environ["SUPPORT_MASTER_KEY"] = good


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
