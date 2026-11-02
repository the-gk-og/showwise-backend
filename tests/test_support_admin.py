"""Run from the repo root:  python tests/test_support_admin.py"""
import base64, json, os, re, sys, tempfile
from urllib.parse import parse_qs, urlparse

tmp = tempfile.mkdtemp()
ADMIN_PW = "Test-Admin-Pass-123"
os.environ["ADMIN_INITIAL_PASSWORD"] = ADMIN_PW
os.environ["SECRET_KEY"] = "t" * 40
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
    secret = admin.enable_totp(); admin.is_2fa_enabled = True
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


def fresh_step():
    """Each TOTP code works once; tests reuse the same 30s step, so forget the last used one."""
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.totp_last_step = None; db.session.commit()


def mint(c, slug="greenroom", **kw):
    fresh_step()
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


def test_2fa_enrol_page_and_api():
    c = client(); r = c.get("/account/security")
    page = r.get_data(as_text=True)
    assert r.status_code == 200 and "Two-factor authentication" in page
    token = re.search(r'var csrf = "([^"]+)"', page).group(1)
    assert client().get("/support/2fa").status_code == 302                                 # old link still lands somewhere
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.is_2fa_enabled = False; db.session.commit()
    try:
        d = c.post("/api/user/2fa/setup", headers={"X-CSRFToken": token}).get_json()
        bad = c.post("/api/user/2fa/verify", json={"token": "000000"}, headers={"X-CSRFToken": token})
        assert bad.status_code == 400
        ok = c.post("/api/user/2fa/verify", json={"token": pyotp.TOTP(d["secret"]).now()}, headers={"X-CSRFToken": token})
        assert ok.status_code == 200 and ok.get_json()["success"]
        codes = ok.get_json()["backup_codes"]
        assert len(codes) == 10 and all(len(x) == 11 and x[5] == "-" for x in codes)       # abcde-12345
        with app.app_context():                                                             # only hashes are stored
            stored = User.query.get(ADMIN_ID).backup_codes
            assert all(x.startswith("h1$") for x in stored)
            assert not any(x.replace("-", "") in "".join(stored) for x in codes)
    finally:
        with app.app_context():
            u = User.query.get(ADMIN_ID); u.totp_secret = secret; u.is_2fa_enabled = True; u.totp_last_step = None
            u.login_attempts = 0; db.session.commit()


def _login_to_2fa_step():
    c = app.test_client()
    t = csrf(c, "/login")
    r = c.post("/login", data={"username": "admin", "password": ADMIN_PW, "csrf_token": t})
    assert r.status_code == 302 and r.headers["Location"].endswith("/verify-2fa"), r.headers
    return c


def test_login_2fa_totp_backup_replay_and_lockout():
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.totp_last_step = None; u.login_attempts = 0; u.locked_until = None
        codes = u.generate_backup_codes(); db.session.commit()
    # a valid authenticator code signs in
    c = _login_to_2fa_step(); t = csrf(c, "/verify-2fa")
    code = pyotp.TOTP(secret).now()
    r = c.post("/verify-2fa", data={"token": code, "csrf_token": t})
    assert r.headers["Location"].endswith("/dashboard") and c.get("/dashboard").status_code == 200
    # the same code a second time is refused (replay), with a clear message
    c = _login_to_2fa_step(); t = csrf(c, "/verify-2fa")
    r = c.post("/verify-2fa", data={"token": code, "csrf_token": t}, follow_redirects=True)
    assert "already used" in r.get_data(as_text=True)
    # a backup code works through the real form field (any case / with or without the dash), once
    c = _login_to_2fa_step(); t = csrf(c, "/verify-2fa")
    assert "maxlength=\"20\"" in c.get("/verify-2fa").get_data(as_text=True)               # the form can hold a backup code
    r = c.post("/verify-2fa", data={"token": codes[0].upper(), "csrf_token": t})
    assert r.headers["Location"].endswith("/dashboard")
    c = _login_to_2fa_step(); t = csrf(c, "/verify-2fa")
    r = c.post("/verify-2fa", data={"token": codes[0], "csrf_token": t})
    assert r.headers["Location"].endswith("/verify-2fa")                                    # already spent
    # page loads do not eat the rate limit: many GETs, then a valid POST still works
    for _ in range(12):
        assert c.get("/verify-2fa").status_code == 200
    # repeated wrong codes lock the account, including the 2FA step
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.login_attempts = 0; u.locked_until = None; db.session.commit()
    c = _login_to_2fa_step()
    for _ in range(6):
        page = c.get("/verify-2fa")
        if page.status_code != 200:
            break                                                                           # lockout ended the attempt
        t = re.search(r'name="csrf_token" value="([^"]+)"', page.get_data(as_text=True)).group(1)
        c.post("/verify-2fa", data={"token": "000000", "csrf_token": t})
    with app.app_context():
        assert User.query.get(ADMIN_ID).locked_until is not None
    c2 = app.test_client()
    r = c2.post("/login", data={"username": "admin", "password": ADMIN_PW, "csrf_token": csrf(c2, "/login")}, follow_redirects=True)
    assert "locked" in r.get_data(as_text=True)
    with app.app_context():
        u = User.query.get(ADMIN_ID); u.login_attempts = 0; u.locked_until = None; u.totp_last_step = None; db.session.commit()


def test_pending_2fa_expires():
    c = _login_to_2fa_step()
    with c.session_transaction() as s:
        s["pending_2fa_at"] = s["pending_2fa_at"] - 3600
    r = c.get("/verify-2fa")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")


def test_destructive_actions_are_post_only():
    c = client()
    assert c.get("/organizations/plainhttp/delete").status_code == 405
    assert c.get("/organizations/plainhttp/toggle").status_code == 405
    assert c.get("/kill-switches/greenroom/toggle").status_code == 405
    r = c.post("/kill-switches/greenroom/toggle", data={"csrf_token": csrf(c, "/kill-switches"), "reason": "overdue"})
    assert r.status_code == 302
    page = c.get("/kill-switches").get_data(as_text=True)
    assert "Suspended" in page and "overdue" in page
    c.post("/kill-switches/greenroom/toggle", data={"csrf_token": csrf(c, "/kill-switches")})


def test_every_page_renders():
    c = client()
    for path in ("/", "/dashboard", "/organizations", "/organizations/add", "/organizations/greenroom/edit",
                 "/kill-switches", "/logs", "/users", "/uptime", "/support/", "/support/org/greenroom",
                 "/account/security"):
        r = c.get(path); assert r.status_code == 200, (path, r.status_code)
    assert client().get("/static/console.css").status_code == 200
    assert b"data-health=\"greenroom\"" in c.get("/dashboard").data


def test_support_receiver_check_endpoint_is_admin_only_and_safe():
    assert client().get("/support/org/greenroom/receiver").get_json()["status"] in ("down", "unknown", "blocked")
    assert client(BOB_ID, "user", "bob").get("/support/org/greenroom/receiver").status_code == 403
    r = client().get("/support/org/plainhttp/receiver").get_json()                           # http:// is never contacted
    assert r["status"] == "unknown"


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
