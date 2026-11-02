"""
Account security for ShowWise Backend: turn two-factor authentication on or off and manage backup codes.

Page:   GET  /account/security
API:    POST /api/user/2fa/setup          start enrolment, returns QR code + manual key
        POST /api/user/2fa/verify         confirm the first code, turns 2FA on, returns backup codes once
        POST /api/user/2fa/disable        needs password and a current code
        POST /api/user/2fa/backup-codes   needs a current code, replaces all backup codes

Backup codes are shown once and stored only as keyed hashes (see models.User.generate_backup_codes).
"""
from flask import Blueprint, jsonify, render_template, request, session

from auth import is_account_locked, lock_account, log_security_event, login_required, verify_second_factor
from models import User, db

bp = Blueprint("account_security", __name__)


def _me():
    user = User.query.get(session.get("user_id"))
    return user if user and user.is_active else None


def _json_body():
    return request.get_json(silent=True) or {}


def _locked_response(user):
    if is_account_locked(user):
        return jsonify({"error": "Too many wrong codes. Try again later."}), 429
    return None


def _bad_code(user, reason, what):
    lock_account(user)
    log_security_event("2fa_check_failed", f"Wrong code while trying to {what}", "warning", user_id=user.id)
    if is_account_locked(user):
        return jsonify({"error": "Too many wrong codes. This account is locked for a while."}), 429
    if reason == "reused":
        return jsonify({"error": "That code was already used. Wait for the next one."}), 400
    return jsonify({"error": "That code is not valid."}), 400


@bp.get("/account/security")
@login_required
def page():
    user = _me()
    return render_template("account_security.html", user=user,
                           enabled=bool(user.is_2fa_enabled),
                           codes_left=user.backup_codes_remaining if user.is_2fa_enabled else 0)


@bp.post("/api/user/2fa/setup")
@login_required
def setup():
    user = _me()
    if user.is_2fa_enabled:
        return jsonify({"error": "2FA is already on. Turn it off first to enrol a new device."}), 409
    secret = user.enable_totp()
    db.session.commit()
    return jsonify({"secret": secret, "qr_code": user.get_totp_qr_code()})


@bp.post("/api/user/2fa/verify")
@login_required
def verify():
    user = _me()
    if user.is_2fa_enabled:
        return jsonify({"error": "2FA is already on."}), 409
    if not user.totp_secret:
        return jsonify({"error": "Start setup first."}), 400
    status = user.check_totp(str(_json_body().get("token", "")))
    if status != "ok":
        msg = "That code was already used. Wait for the next one." if status == "reused" else "That code is not valid."
        return jsonify({"error": msg}), 400
    user.is_2fa_enabled = True
    codes = user.generate_backup_codes()
    db.session.commit()
    log_security_event("2fa_enabled", "Two-factor authentication turned on", "info", user_id=user.id)
    return jsonify({"success": True, "backup_codes": codes})


@bp.post("/api/user/2fa/disable")
@login_required
def disable():
    user = _me()
    if not user.is_2fa_enabled:
        return jsonify({"error": "2FA is not on."}), 409
    blocked = _locked_response(user)
    if blocked:
        return blocked
    data = _json_body()
    if not user.check_password(str(data.get("password", ""))):
        lock_account(user)
        log_security_event("2fa_check_failed", "Wrong password while turning 2FA off", "warning", user_id=user.id)
        return jsonify({"error": "That password is not correct."}), 400
    ok, reason = verify_second_factor(user, str(data.get("code", "")))
    if not ok:
        return _bad_code(user, reason, "turn 2FA off")
    user.disable_totp()
    db.session.commit()
    log_security_event("2fa_disabled", "Two-factor authentication turned off", "warning", user_id=user.id)
    return jsonify({"success": True})


@bp.post("/api/user/2fa/backup-codes")
@login_required
def new_backup_codes():
    user = _me()
    if not user.is_2fa_enabled:
        return jsonify({"error": "Turn on 2FA first."}), 409
    blocked = _locked_response(user)
    if blocked:
        return blocked
    code = str(_json_body().get("code", ""))
    digits = code.replace(" ", "")
    if not (digits.isdigit() and len(digits) == 6):
        return jsonify({"error": "Enter the 6-digit code from your authenticator app."}), 400
    ok, reason = verify_second_factor(user, digits)
    if not ok:
        return _bad_code(user, reason, "make new backup codes")
    codes = user.generate_backup_codes()
    db.session.commit()
    log_security_event("2fa_backup_codes_reset", "Backup codes replaced", "info", user_id=user.id)
    return jsonify({"success": True, "backup_codes": codes})


def init_account_security(app, limiter=None):
    app.register_blueprint(bp)
    if limiter is not None:
        for ep, rule in (("account_security.setup", "20 per hour"),
                         ("account_security.verify", "15 per minute"),
                         ("account_security.disable", "10 per minute"),
                         ("account_security.new_backup_codes", "10 per minute")):
            app.view_functions[ep] = limiter.limit(rule)(app.view_functions[ep])
