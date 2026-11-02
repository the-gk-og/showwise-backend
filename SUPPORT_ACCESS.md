# Support access portal

Log in to a customer's ShowWise instance for support from the backend, with no manual key handling.
Instances are your Organizations (slug = instance ID, url = where the instance lives).

## One-time setup (backend)
1. `pip install -r requirements.txt` (adds `cryptography`).
2. Create a master key and add it to the backend env (not in git, not in the database):
       python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
       SUPPORT_MASTER_KEY=<value>
   It encrypts the signing key stored in the `support_signing_keys` table. The table is created
   automatically on first visit, no migration needed.
3. Restart, sign in as an admin, open **Support** in the nav. The first visit generates the signing key.
4. Turn on 2FA for your admin account at `/account/security`. Support logins
   require a fresh authenticator code. Set `SUPPORT_REQUIRE_2FA=0` only for local testing.

## Per customer instance (once)
Open Support -> the organization. Copy the env block into that instance's environment:

    SUPPORT_PUBLIC_KEY=...        # same for every instance; lists several keys during rotation
    SUPPORT_INSTANCE_ID=<slug>
    SUPPORT_TRUST_PROXY_HEADERS=1 # behind Cloudflare Tunnel

The instance runs `support_access.py` (separate patch for the crew app). Until it is configured,
`/support/login` there returns 404.

## Using it
Support -> organization -> pick read-only or admin, duration (5-30 min), a reason, and your 2FA code ->
**Log in**. You are redirected into the instance with a single-use token. A red banner shows on the
instance for the whole session, and the instance keeps its own audit log that the customer's admins can read.

## What is recorded and enforced
- Every mint is a Log entry (type `support_login`, level warning) with admin, instance, scope, duration,
  reason and token id. Filter the Logs page by type `support_login`. Denied attempts are `support_denied`;
  key rotation, revoke and per-org enable/disable are `support_config`.
- Admin session + fresh TOTP required; wrong codes use the same failed-attempt lockout as normal login.
- 20 mints per hour per IP. Mint responses are `no-store` and redirect with `Referrer-Policy: no-referrer`.
- Per-organization **Disable support access** button blocks minting for that org (stored in `settings`).
- The org URL must be https:// (http only for localhost, or `SUPPORT_ALLOW_HTTP=1`).

## Checking an instance is ready
Support -> an organization shows a **Receiver** chip. *Receiver on* means the instance answers at
`/support/login`. *Not set up* means its env vars are missing or it does not include `support_access.py` yet.

## Locked out of 2FA
Each authenticator code works once, backup codes (shown once at setup) work once each. If you lose both, on the server:
`flask --app app_db reset-2fa <username>`, then sign in and turn 2FA on again.

## Key rotation
Rotate -> paste the new `SUPPORT_PUBLIC_KEY` (new key + old key) on every instance -> Revoke the old key.

## Security notes
- This backend can now sign in to every customer. Keep admin accounts on strong passwords + 2FA and put
  the backend behind Tailscale/Cloudflare Access if you can.
- The key is encrypted at rest, which protects DB copies and backups, not someone controlling the running
  server and its env.
- `auth.get_client_ip()` trusts `X-Forwarded-For` as sent. Behind a proxy that overwrites it that's fine;
  otherwise the IPs in logs can be spoofed.

## Tests
    python tests/test_support_admin.py
