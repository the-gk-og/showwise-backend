"""
Support access portal for the ShowWise backend.

Log in to a customer's ShowWise instance for support without handling keys by hand:
  * Instances are your existing Organizations (slug = instance ID, url = base URL).
  * The backend holds an Ed25519 signing key, stored Fernet-encrypted in the database.
  * "Support login" mints a short-lived, single-use token bound to that one instance and
    redirects you to <org.url>/support/login?token=... (receiver: support_access.py).
  * Needs an admin session AND a fresh TOTP code (your existing 2FA); every mint is written
    to the Logs page as type "support_login".

Env: SUPPORT_MASTER_KEY (required), SUPPORT_REQUIRE_2FA ("0" to disable in dev),
     SUPPORT_ALLOW_HTTP ("1" to allow http:// instance URLs; localhost always allowed).
"""
import base64
import json
import os
import re
import time
import uuid
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import serialization as ser
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func

from auth import admin_required, lock_account, log_security_event, login_required
from models import Log, Organization, Setting, SupportSigningKey, User, db

ISSUER = "showwise-support"
SCOPES = ("readonly", "admin")
MINUTES = (5, 10, 15, 30)
LOGIN_PATH = "/support/login"
DISABLED_KEY = "support_access_disabled"

support_bp = Blueprint("support", __name__, url_prefix="/support")


# ---------------------------------------------------------------------- keys
def _fernet():
    k = os.environ.get("SUPPORT_MASTER_KEY", "").strip()
    try:
        return Fernet(k.encode()) if k else None
    except Exception:
        return None


def _ready():
    if _fernet() is None:
        return False
    SupportSigningKey.__table__.create(db.engine, checkfirst=True)  # no migration step needed
    return True


def _active_key():
    row = SupportSigningKey.query.filter_by(status="active").first()
    if row is None:
        row = _new_key("active")
    return row


def _new_key(status):
    priv = Ed25519PrivateKey.generate()
    raw = priv.private_bytes(ser.Encoding.Raw, ser.PrivateFormat.Raw, ser.NoEncryption())
    pub = priv.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw)
    row = SupportSigningKey(kid=uuid.uuid4().hex[:8], status=status,
                            public_b64=base64.urlsafe_b64encode(pub).decode(),
                            private_enc=_fernet().encrypt(raw).decode())
    db.session.add(row)
    db.session.commit()
    return row


def _load_private(row):
    try:
        return Ed25519PrivateKey.from_private_bytes(_fernet().decrypt(row.private_enc.encode()))
    except InvalidToken:
        abort(500, "SUPPORT_MASTER_KEY does not match the stored signing key.")


def public_keys_env():
    """SUPPORT_PUBLIC_KEY value for instances: active key first, then retired keys still in grace."""
    rows = SupportSigningKey.query.filter(SupportSigningKey.status.in_(("active", "retired"))) \
        .order_by((SupportSigningKey.status == "active").desc(), SupportSigningKey.created_at.desc()).all()
    return ",".join(r.public_b64 for r in rows)


def mint_token(priv, instance_id, operator, scope, minutes, now=None):
    now = int(time.time() if now is None else now)
    payload = {"iss": ISSUER, "aud": instance_id, "sub": operator, "scope": scope,
               "iat": now, "exp": now + minutes * 60, "jti": uuid.uuid4().hex}
    pb = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    enc = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    return enc(pb) + "." + enc(priv.sign(pb)), payload["jti"]


# ------------------------------------------------------------------- helpers
@support_bp.app_template_filter("sfmt")
def _sfmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "never"


def _org_or_404(slug):
    org = Organization.query.filter_by(slug=slug).first()
    if org is None:
        abort(404)
    return org


def _org_enabled(org):
    return not Setting.query.filter_by(organization_id=org.id, key=DISABLED_KEY, value="1").first()


def _clean_url(u):
    p = urlparse((u or "").strip())
    local = p.hostname in ("localhost", "127.0.0.1")
    if p.scheme != "https" and not (p.scheme == "http" and (local or os.environ.get("SUPPORT_ALLOW_HTTP") == "1")):
        return None
    if not p.netloc or p.username or p.password or p.query or p.fragment:
        return None
    return f"{p.scheme}://{p.netloc}{p.path.rstrip('/')}"


def _require_2fa():
    return os.environ.get("SUPPORT_REQUIRE_2FA", "1") != "0"


def _operator(user):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", user.username)[:32] or "admin"


def _recent(org=None, limit=15):
    q = Log.query.filter(Log.log_type == "support_login")
    if org is not None:
        q = q.filter(Log.organization_id == org.id)
    return q.order_by(Log.created_at.desc()).limit(limit).all()


# --------------------------------------------------------------------- views
@support_bp.after_request
def _no_store(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp


@support_bp.get("/")
@login_required
@admin_required
def index():
    if not _ready():
        return render_template("support.html", ready=False), 503
    _active_key()
    last = dict(db.session.query(Log.organization_id, func.max(Log.created_at))
                .filter(Log.log_type == "support_login").group_by(Log.organization_id).all())
    disabled = {s.organization_id for s in Setting.query.filter_by(key=DISABLED_KEY, value="1")}
    keys = SupportSigningKey.query.filter(SupportSigningKey.status != "revoked") \
        .order_by(SupportSigningKey.created_at.desc()).all()
    return render_template("support.html", ready=True, orgs=Organization.query.order_by(Organization.name).all(),
                           last=last, disabled=disabled, keys=keys, env=public_keys_env(), recent=_recent())


@support_bp.get("/org/<slug>")
@login_required
@admin_required
def org_page(slug):
    if not _ready():
        abort(503)
    org = _org_or_404(slug)
    _active_key()
    return render_template("support_org.html", org=org, enabled=_org_enabled(org), env=public_keys_env(),
                           url_ok=_clean_url(org.url), minutes=MINUTES, need_2fa=_require_2fa(),
                           me=User.query.get(session["user_id"]), recent=_recent(org))


@support_bp.post("/org/<slug>/login")
@login_required
@admin_required
def login_to_org(slug):
    if not _ready():
        abort(503)
    org, user = _org_or_404(slug), User.query.get(session["user_id"])
    back = redirect(url_for("support.org_page", slug=slug))
    scope = request.form.get("scope")
    reason = (request.form.get("reason") or "").strip()[:200]
    try:
        minutes = int(request.form.get("minutes", 10))
    except ValueError:
        minutes = 0
    base = _clean_url(org.url)
    if scope not in SCOPES or minutes not in MINUTES or len(reason) < 3:
        flash("Choose an access level and duration, and give a reason (3+ characters).", "error")
        return back
    if not base:
        flash("This organization has no valid https:// URL set. Edit the organization first.", "error")
        return back
    if not _org_enabled(org):
        flash("Support access is disabled for this organization.", "error")
        return back
    if _require_2fa():
        if not user.is_2fa_enabled:
            flash("Turn on 2FA for your account before using support access.", "error")
            return back
        if not user.verify_totp((request.form.get("totp") or "").replace(" ", "")):
            lock_account(user)  # same counter/lockout as the normal login
            log_security_event("support_denied", f"Bad 2FA code for support login to {org.slug}",
                               "warning", user_id=user.id, org_id=org.id)
            flash("Invalid 2FA code.", "error")
            return back

    token, jti = mint_token(_load_private(_active_key()), org.slug, _operator(user), scope, minutes)
    log_security_event("support_login",
                       f"Support login to {org.slug} by {user.username}: {scope}, {minutes} min. Reason: {reason}",
                       "warning", user_id=user.id, org_id=org.id,
                       metadata={"scope": scope, "minutes": minutes, "reason": reason, "jti": jti})
    resp = redirect(f"{base}{LOGIN_PATH}?token={token}", code=303)
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@support_bp.get("/2fa")
@login_required
@admin_required
def twofa_page():
    """Tiny self-serve 2FA setup that drives the existing /api/user/2fa/* endpoints."""
    return render_template("support_2fa.html", enabled=bool(User.query.get(session["user_id"]).is_2fa_enabled))


@support_bp.post("/org/<slug>/toggle")
@login_required
@admin_required
def toggle_org(slug):
    org = _org_or_404(slug)
    row = Setting.query.filter_by(organization_id=org.id, key=DISABLED_KEY).first()
    if row is None:
        row = Setting(organization_id=org.id, key=DISABLED_KEY, value="0")
        db.session.add(row)
    row.value = "0" if row.value == "1" else "1"
    db.session.commit()
    log_security_event("support_config", f"Support access {'disabled' if row.value == '1' else 'enabled'} for {org.slug}",
                       "warning", user_id=session["user_id"], org_id=org.id)
    return redirect(url_for("support.org_page", slug=slug))


@support_bp.post("/keys/rotate")
@login_required
@admin_required
def key_rotate():
    if not _ready():
        abort(503)
    SupportSigningKey.query.filter_by(status="active").update({"status": "retired"})
    db.session.commit()
    row = _new_key("active")
    log_security_event("support_config", f"Support signing key rotated (new key {row.kid})", "warning",
                       user_id=session["user_id"])
    flash("New signing key is active. Update SUPPORT_PUBLIC_KEY on instances, then revoke the old key.", "success")
    return redirect(url_for("support.index"))


@support_bp.post("/keys/<kid>/revoke")
@login_required
@admin_required
def key_revoke(kid):
    row = SupportSigningKey.query.filter_by(kid=kid, status="retired").first()
    if row:
        row.status, row.private_enc = "revoked", ""
        db.session.commit()
        log_security_event("support_config", f"Support signing key {kid} revoked", "warning",
                           user_id=session["user_id"])
    return redirect(url_for("support.index"))


def init_support_admin(app, limiter=None):
    app.register_blueprint(support_bp)
    if limiter is not None:  # minting is also rate limited per IP
        ep = "support.login_to_org"
        app.view_functions[ep] = limiter.limit("20 per hour")(app.view_functions[ep])
