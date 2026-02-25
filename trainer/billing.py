"""Subscription billing + login flows for hosted trainer deployments."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:  # pragma: no cover - runtime dependency in production
    import stripe
except ModuleNotFoundError:  # pragma: no cover - allows local tests without stripe installed
    stripe = None

ACTIVE_SUBSCRIPTION_STATUSES = {"active", "trialing"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ValueError("Valid email is required")
    return email


def _hash_value(secret_key: str, value: str) -> str:
    return hmac.new(
        secret_key.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@dataclass(frozen=True)
class BillingConfig:
    stripe_secret_key: str
    stripe_webhook_secret: str
    stripe_price_id: str
    session_ttl_seconds: int
    login_code_ttl_seconds: int
    login_code_cooldown_seconds: int
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_from_email: str
    expose_login_codes: bool


class BillingStore:
    """Persistence for subscriptions, login codes, and web sessions."""

    def __init__(self, db_path: Path, secret_key: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.secret_key = secret_key
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    email TEXT PRIMARY KEY,
                    stripe_customer_id TEXT UNIQUE,
                    stripe_subscription_id TEXT UNIQUE,
                    status TEXT NOT NULL,
                    current_period_end INTEGER,
                    updated_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS login_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_login_codes_email_created
                ON login_codes(email, created_at DESC)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS web_sessions (
                    session_hash TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_web_sessions_email
                ON web_sessions(email)
                """
            )

    def purge_expired(self) -> None:
        now = int(time.time())
        with self._connect() as conn:
            conn.execute("DELETE FROM login_codes WHERE expires_at <= ?", (now,))
            conn.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (now,))

    def upsert_subscription(
        self,
        *,
        email: str,
        stripe_customer_id: Optional[str],
        stripe_subscription_id: Optional[str],
        status: str,
        current_period_end: Optional[int],
        raw_payload: Dict[str, Any],
    ) -> None:
        normalized = normalize_email(email)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (
                    email,
                    stripe_customer_id,
                    stripe_subscription_id,
                    status,
                    current_period_end,
                    updated_at,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    status = excluded.status,
                    current_period_end = excluded.current_period_end,
                    updated_at = excluded.updated_at,
                    raw_json = excluded.raw_json
                """,
                (
                    normalized,
                    stripe_customer_id or None,
                    stripe_subscription_id or None,
                    str(status or "").strip().lower() or "incomplete",
                    int(current_period_end) if current_period_end else None,
                    _utc_now_iso(),
                    json.dumps(raw_payload or {}, separators=(",", ":")),
                ),
            )

    def subscription_for_email(self, email: str) -> Optional[Dict[str, Any]]:
        normalized = normalize_email(email)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    email,
                    stripe_customer_id,
                    stripe_subscription_id,
                    status,
                    current_period_end,
                    updated_at
                FROM subscriptions
                WHERE email = ?
                """,
                (normalized,),
            ).fetchone()
        if not row:
            return None
        return {
            "email": row["email"],
            "stripe_customer_id": row["stripe_customer_id"],
            "stripe_subscription_id": row["stripe_subscription_id"],
            "status": row["status"],
            "current_period_end": row["current_period_end"],
            "updated_at": row["updated_at"],
        }

    def email_for_customer_id(self, stripe_customer_id: str) -> Optional[str]:
        customer_id = str(stripe_customer_id or "").strip()
        if not customer_id:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email FROM subscriptions WHERE stripe_customer_id = ?",
                (customer_id,),
            ).fetchone()
        if not row:
            return None
        return str(row["email"])

    def subscription_active(self, email: str, *, now_ts: Optional[int] = None) -> bool:
        info = self.subscription_for_email(email)
        if not info:
            return False
        status = str(info.get("status") or "").lower()
        if status not in ACTIVE_SUBSCRIPTION_STATUSES:
            return False
        period_end = info.get("current_period_end")
        if period_end is None:
            return True
        if now_ts is None:
            now_ts = int(time.time())
        return int(period_end) > int(now_ts)

    def create_login_code(
        self,
        email: str,
        *,
        ttl_seconds: int,
        cooldown_seconds: int,
    ) -> str:
        normalized = normalize_email(email)
        now = int(time.time())
        self.purge_expired()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT created_at
                FROM login_codes
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if row and cooldown_seconds > 0:
                if int(now - int(row["created_at"])) < int(cooldown_seconds):
                    raise ValueError("Please wait before requesting another login code")
            code = f"{secrets.randbelow(1_000_000):06d}"
            code_hash = _hash_value(self.secret_key, f"login-code:{normalized}:{code}")
            conn.execute(
                """
                INSERT INTO login_codes (
                    email,
                    code_hash,
                    created_at,
                    expires_at,
                    attempts
                )
                VALUES (?, ?, ?, ?, 0)
                """,
                (
                    normalized,
                    code_hash,
                    now,
                    now + int(ttl_seconds),
                ),
            )
        return code

    def verify_login_code(
        self,
        email: str,
        code: str,
        *,
        max_attempts: int = 6,
    ) -> bool:
        normalized = normalize_email(email)
        candidate = str(code or "").strip()
        if not candidate:
            return False
        now = int(time.time())
        expected_hash = _hash_value(self.secret_key, f"login-code:{normalized}:{candidate}")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, code_hash, attempts, expires_at
                FROM login_codes
                WHERE email = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (normalized,),
            ).fetchone()
            if not row:
                return False
            if int(row["expires_at"]) <= now:
                conn.execute("DELETE FROM login_codes WHERE id = ?", (int(row["id"]),))
                return False
            if hmac.compare_digest(str(row["code_hash"]), expected_hash):
                conn.execute("DELETE FROM login_codes WHERE email = ?", (normalized,))
                return True
            attempts = int(row["attempts"]) + 1
            if attempts >= max_attempts:
                conn.execute("DELETE FROM login_codes WHERE id = ?", (int(row["id"]),))
            else:
                conn.execute(
                    "UPDATE login_codes SET attempts = ? WHERE id = ?",
                    (attempts, int(row["id"])),
                )
            return False

    def create_session(self, email: str, *, ttl_seconds: int) -> str:
        normalized = normalize_email(email)
        now = int(time.time())
        token = secrets.token_urlsafe(48)
        session_hash = _hash_value(self.secret_key, f"session:{token}")
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO web_sessions (
                    session_hash,
                    email,
                    created_at,
                    expires_at,
                    last_seen_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    session_hash,
                    normalized,
                    now,
                    now + int(ttl_seconds),
                    now,
                ),
            )
        return token

    def session_email(self, token: str) -> Optional[str]:
        raw = str(token or "").strip()
        if not raw:
            return None
        self.purge_expired()
        now = int(time.time())
        session_hash = _hash_value(self.secret_key, f"session:{raw}")
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT email, expires_at
                FROM web_sessions
                WHERE session_hash = ?
                """,
                (session_hash,),
            ).fetchone()
            if not row:
                return None
            if int(row["expires_at"]) <= now:
                conn.execute("DELETE FROM web_sessions WHERE session_hash = ?", (session_hash,))
                return None
            conn.execute(
                """
                UPDATE web_sessions
                SET last_seen_at = ?
                WHERE session_hash = ?
                """,
                (now, session_hash),
            )
            return str(row["email"])

    def revoke_session(self, token: str) -> None:
        raw = str(token or "").strip()
        if not raw:
            return
        session_hash = _hash_value(self.secret_key, f"session:{raw}")
        with self._connect() as conn:
            conn.execute("DELETE FROM web_sessions WHERE session_hash = ?", (session_hash,))

    def revoke_sessions_for_email(self, email: str) -> None:
        normalized = normalize_email(email)
        with self._connect() as conn:
            conn.execute("DELETE FROM web_sessions WHERE email = ?", (normalized,))


class MailgunClient:
    """Mailgun sender for one-time login codes."""

    def __init__(
        self,
        *,
        api_key: str,
        domain: str,
        from_email: str,
        timeout_seconds: int = 12,
    ):
        self.api_key = str(api_key or "").strip()
        self.domain = str(domain or "").strip()
        self.from_email = str(from_email or "").strip()
        self.timeout_seconds = int(timeout_seconds)

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.domain and self.from_email)

    def send_login_code(self, email: str, code: str, ttl_minutes: int) -> None:
        if not self.configured:
            raise RuntimeError("Mailgun is not configured")
        to_email = normalize_email(email)
        payload = urlencode(
            {
                "from": self.from_email,
                "to": to_email,
                "subject": "Your Poker Trainer login code",
                "text": (
                    f"Your Poker Trainer login code is {code}.\n\n"
                    f"It expires in {ttl_minutes} minutes.\n"
                    "If you did not request this code, you can ignore this email."
                ),
            }
        ).encode("utf-8")
        auth = base64.b64encode(f"api:{self.api_key}".encode("utf-8")).decode("utf-8")
        req = Request(
            url=f"https://api.mailgun.net/v3/{self.domain}/messages",
            data=payload,
            method="POST",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urlopen(req, timeout=self.timeout_seconds) as resp:
            status = getattr(resp, "status", 200)
            if int(status) >= 400:
                raise RuntimeError(f"Mailgun rejected request with status {status}")


class BillingService:
    """High-level billing operations against Stripe + local auth state."""

    def __init__(self, config: BillingConfig, store: BillingStore):
        self.config = config
        self.store = store
        self.mailgun = MailgunClient(
            api_key=config.mailgun_api_key,
            domain=config.mailgun_domain,
            from_email=config.mailgun_from_email,
        )
        if stripe is not None and self.config.stripe_secret_key:
            stripe.api_key = self.config.stripe_secret_key

    @property
    def enabled(self) -> bool:
        return bool(stripe is not None and self.config.stripe_secret_key and self.config.stripe_price_id)

    def _require_enabled(self) -> None:
        if not self.enabled:
            if stripe is None:
                raise RuntimeError("stripe package is not installed")
            raise RuntimeError("Billing is not configured")

    def create_checkout_session(
        self,
        *,
        email: str,
        success_url: str,
        cancel_url: str,
    ) -> Dict[str, str]:
        self._require_enabled()
        normalized = normalize_email(email)
        kwargs: Dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": self.config.stripe_price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,
            "billing_address_collection": "auto",
            "metadata": {"product": "poker-trainer"},
        }
        known = self.store.subscription_for_email(normalized)
        known_customer = (known or {}).get("stripe_customer_id")
        if known_customer:
            kwargs["customer"] = known_customer
        else:
            kwargs["customer_email"] = normalized

        session = stripe.checkout.Session.create(**kwargs)
        return {"id": str(session["id"]), "url": str(session["url"])}

    @staticmethod
    def _to_dict(value: Any) -> Dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "to_dict_recursive"):
            return value.to_dict_recursive()
        return dict(value)

    def _email_for_customer(self, stripe_customer_id: Optional[str]) -> Optional[str]:
        customer_id = str(stripe_customer_id or "").strip()
        if not customer_id:
            return None
        cached = self.store.email_for_customer_id(customer_id)
        if cached:
            return cached
        customer = stripe.Customer.retrieve(customer_id)
        email = str((self._to_dict(customer)).get("email") or "").strip().lower()
        if not email:
            return None
        return normalize_email(email)

    def _sync_subscription(self, subscription: Any, fallback_email: Optional[str] = None) -> Dict[str, Any]:
        sub = self._to_dict(subscription)
        customer_ref = sub.get("customer")
        customer_id = customer_ref.get("id") if isinstance(customer_ref, dict) else customer_ref
        customer_id = str(customer_id or "").strip() or None

        email = normalize_email(fallback_email) if fallback_email else None
        if not email:
            email = self._email_for_customer(customer_id)
        if not email:
            raise ValueError("Could not resolve subscription email")

        status = str(sub.get("status") or "incomplete").strip().lower()
        period_end_raw = sub.get("current_period_end")
        period_end = int(period_end_raw) if period_end_raw else None
        sub_id = str(sub.get("id") or "").strip() or None
        self.store.upsert_subscription(
            email=email,
            stripe_customer_id=customer_id,
            stripe_subscription_id=sub_id,
            status=status,
            current_period_end=period_end,
            raw_payload=sub,
        )
        if not self.store.subscription_active(email):
            self.store.revoke_sessions_for_email(email)
        return {
            "email": email,
            "status": status,
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": sub_id,
            "current_period_end": period_end,
        }

    def sync_checkout_session(self, session_id: str) -> Dict[str, Any]:
        self._require_enabled()
        raw_session_id = str(session_id or "").strip()
        if not raw_session_id:
            raise ValueError("session_id is required")

        session = stripe.checkout.Session.retrieve(
            raw_session_id,
            expand=["subscription", "customer"],
        )
        obj = self._to_dict(session)
        status = str(obj.get("status") or "").lower()
        if status != "complete":
            raise ValueError("Checkout session is not complete")

        customer_details = obj.get("customer_details") or {}
        email = str(customer_details.get("email") or "").strip().lower()
        if not email:
            customer_obj = obj.get("customer") or {}
            if isinstance(customer_obj, dict):
                email = str(customer_obj.get("email") or "").strip().lower()
        if not email:
            raise ValueError("Checkout session is missing customer email")

        sub = obj.get("subscription")
        if isinstance(sub, str):
            sub = stripe.Subscription.retrieve(sub)
        if not sub:
            raise ValueError("Checkout session is missing subscription")
        result = self._sync_subscription(sub, fallback_email=email)
        result["checkout_session_id"] = raw_session_id
        return result

    def handle_webhook(self, payload: bytes, signature_header: str) -> Dict[str, str]:
        self._require_enabled()
        if not self.config.stripe_webhook_secret:
            raise RuntimeError("Stripe webhook secret is not configured")
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=signature_header,
            secret=self.config.stripe_webhook_secret,
        )
        event_type = str(event["type"])
        data_object = event["data"]["object"]

        if event_type == "checkout.session.completed":
            obj = self._to_dict(data_object)
            if str(obj.get("mode")) == "subscription":
                self.sync_checkout_session(str(obj.get("id") or ""))

        elif event_type in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            self._sync_subscription(data_object)

        elif event_type in {"invoice.paid", "invoice.payment_failed"}:
            obj = self._to_dict(data_object)
            sub_id = str(obj.get("subscription") or "").strip()
            if sub_id:
                sub = stripe.Subscription.retrieve(sub_id)
                self._sync_subscription(sub)

        return {
            "event_id": str(event.get("id") or ""),
            "event_type": event_type,
        }

    def request_login_code(self, email: str) -> Dict[str, Any]:
        normalized = normalize_email(email)
        if not self.store.subscription_active(normalized):
            raise PermissionError("No active subscription found for this email")
        code = self.store.create_login_code(
            normalized,
            ttl_seconds=self.config.login_code_ttl_seconds,
            cooldown_seconds=self.config.login_code_cooldown_seconds,
        )

        response: Dict[str, Any] = {
            "ok": True,
            "expires_in_seconds": int(self.config.login_code_ttl_seconds),
        }
        if self.mailgun.configured:
            ttl_minutes = max(1, int(self.config.login_code_ttl_seconds / 60))
            self.mailgun.send_login_code(normalized, code, ttl_minutes)
        elif self.config.expose_login_codes:
            response["debug_code"] = code
        else:
            raise RuntimeError(
                "Mailgun is required for login code delivery in production mode"
            )
        return response

    def verify_login_code(self, email: str, code: str) -> str:
        normalized = normalize_email(email)
        if not self.store.subscription_active(normalized):
            raise PermissionError("Subscription is inactive")
        ok = self.store.verify_login_code(normalized, str(code or "").strip())
        if not ok:
            raise PermissionError("Invalid or expired login code")
        return self.store.create_session(
            normalized,
            ttl_seconds=self.config.session_ttl_seconds,
        )

    def create_session_for_email(self, email: str) -> str:
        normalized = normalize_email(email)
        if not self.store.subscription_active(normalized):
            raise PermissionError("Subscription is inactive")
        return self.store.create_session(
            normalized,
            ttl_seconds=self.config.session_ttl_seconds,
        )

    def session_email(self, token: str) -> Optional[str]:
        email = self.store.session_email(token)
        if not email:
            return None
        if not self.store.subscription_active(email):
            self.store.revoke_session(token)
            return None
        return email

    def logout(self, token: str) -> None:
        self.store.revoke_session(token)

    def create_portal_session(self, email: str, return_url: str) -> Dict[str, str]:
        self._require_enabled()
        info = self.store.subscription_for_email(email)
        if not info:
            raise ValueError("No billing profile found for this user")
        customer_id = str(info.get("stripe_customer_id") or "").strip()
        if not customer_id:
            raise ValueError("No Stripe customer linked for this user")
        portal = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return {"url": str(portal["url"])}
