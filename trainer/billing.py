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

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ELITE = "elite"
PLAN_TIERS = {PLAN_FREE, PLAN_PRO, PLAN_ELITE}
PAID_PLAN_TIERS = {PLAN_PRO, PLAN_ELITE}

PLAN_ENTITLEMENTS: Dict[str, Dict[str, Any]] = {
    PLAN_FREE: {
        "tier": PLAN_FREE,
        "label": "Free",
        "monthly_price_usd": 0,
        "max_upload_hands": 500,
        "max_aliases_per_profile": 12,
        "max_compare_groups": 1,
        "show_exploits": False,
        "allow_multi_profile_compare": False,
        "allow_training_workbench": False,
        "allow_live_training": False,
    },
    PLAN_PRO: {
        "tier": PLAN_PRO,
        "label": "Pro",
        "monthly_price_usd": 29,
        "max_upload_hands": 2000,
        "max_aliases_per_profile": 20,
        "max_compare_groups": 2,
        "show_exploits": True,
        "allow_multi_profile_compare": True,
        "allow_training_workbench": False,
        "allow_live_training": False,
    },
    PLAN_ELITE: {
        "tier": PLAN_ELITE,
        "label": "Elite",
        "monthly_price_usd": 79,
        "max_upload_hands": 6000,
        "max_aliases_per_profile": 30,
        "max_compare_groups": 4,
        "show_exploits": True,
        "allow_multi_profile_compare": True,
        "allow_training_workbench": True,
        "allow_live_training": True,
    },
}


def normalize_plan_tier(value: str, *, default: str = PLAN_FREE) -> str:
    tier = str(value or "").strip().lower()
    if tier in PLAN_TIERS:
        return tier
    return default


def plan_entitlements(tier: str) -> Dict[str, Any]:
    key = normalize_plan_tier(tier, default=PLAN_FREE)
    return dict(PLAN_ENTITLEMENTS[key])


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
    stripe_price_id_pro: str
    stripe_price_id_elite: str
    session_ttl_seconds: int
    login_code_ttl_seconds: int
    login_code_cooldown_seconds: int
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_from_email: str
    allow_free_tier: bool
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
                    plan_tier TEXT NOT NULL DEFAULT 'free',
                    current_period_end INTEGER,
                    updated_at TEXT NOT NULL,
                    raw_json TEXT NOT NULL
                )
                """
            )
            self._ensure_column(
                conn,
                table="subscriptions",
                column="plan_tier",
                definition="TEXT NOT NULL DEFAULT 'free'",
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

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        *,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        present = {str(row["name"]).strip().lower() for row in rows}
        if column.lower() in present:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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
        plan_tier: str,
        current_period_end: Optional[int],
        raw_payload: Dict[str, Any],
    ) -> None:
        normalized = normalize_email(email)
        resolved_plan = normalize_plan_tier(plan_tier, default=PLAN_FREE)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (
                    email,
                    stripe_customer_id,
                    stripe_subscription_id,
                    status,
                    plan_tier,
                    current_period_end,
                    updated_at,
                    raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    stripe_customer_id = excluded.stripe_customer_id,
                    stripe_subscription_id = excluded.stripe_subscription_id,
                    status = excluded.status,
                    plan_tier = excluded.plan_tier,
                    current_period_end = excluded.current_period_end,
                    updated_at = excluded.updated_at,
                    raw_json = excluded.raw_json
                """,
                (
                    normalized,
                    stripe_customer_id or None,
                    stripe_subscription_id or None,
                    str(status or "").strip().lower() or "incomplete",
                    resolved_plan,
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
                    plan_tier,
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
            "plan_tier": normalize_plan_tier(row["plan_tier"], default=PLAN_FREE),
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
        plan_tier = normalize_plan_tier(str(info.get("plan_tier") or PLAN_FREE))
        if status == "free" and plan_tier == PLAN_FREE:
            return True
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
        return bool(stripe is not None and self.config.stripe_secret_key and self.checkout_enabled_tiers())

    def checkout_enabled_tiers(self) -> list[str]:
        enabled: list[str] = []
        if str(self.config.stripe_price_id_pro or "").strip():
            enabled.append(PLAN_PRO)
        if str(self.config.stripe_price_id_elite or "").strip():
            enabled.append(PLAN_ELITE)
        return enabled

    def _price_id_for_tier(self, tier: str) -> str:
        normalized_tier = normalize_plan_tier(tier, default=PLAN_PRO)
        if normalized_tier == PLAN_ELITE:
            return str(self.config.stripe_price_id_elite or "").strip()
        return str(self.config.stripe_price_id_pro or "").strip()

    def _plan_tier_for_price_id(self, price_id: str) -> str:
        candidate = str(price_id or "").strip()
        if not candidate:
            return PLAN_PRO
        if candidate == str(self.config.stripe_price_id_elite or "").strip():
            return PLAN_ELITE
        if candidate == str(self.config.stripe_price_id_pro or "").strip():
            return PLAN_PRO
        return PLAN_PRO

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
        plan_tier: str = PLAN_PRO,
    ) -> Dict[str, str]:
        self._require_enabled()
        normalized = normalize_email(email)
        selected_tier = normalize_plan_tier(plan_tier, default=PLAN_PRO)
        if selected_tier not in PAID_PLAN_TIERS:
            raise ValueError("Use email login for the free tier")
        price_id = self._price_id_for_tier(selected_tier)
        if not price_id:
            raise ValueError(f"Checkout is not configured for plan: {selected_tier}")
        kwargs: Dict[str, Any] = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "allow_promotion_codes": True,
            "billing_address_collection": "auto",
            "metadata": {"product": "poker-trainer", "plan_tier": selected_tier},
        }
        known = self.store.subscription_for_email(normalized)
        known_customer = (known or {}).get("stripe_customer_id")
        if known_customer:
            kwargs["customer"] = known_customer
        else:
            kwargs["customer_email"] = normalized

        session = stripe.checkout.Session.create(**kwargs)
        return {"id": str(session["id"]), "url": str(session["url"]), "plan_tier": selected_tier}

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

        metadata = sub.get("metadata") if isinstance(sub.get("metadata"), dict) else {}
        plan_tier = normalize_plan_tier(str((metadata or {}).get("plan_tier") or ""), default=PLAN_PRO)
        if plan_tier == PLAN_FREE:
            plan_tier = PLAN_PRO
        if not metadata or "plan_tier" not in metadata:
            items = sub.get("items")
            data_rows = []
            if isinstance(items, dict):
                data_rows = items.get("data") if isinstance(items.get("data"), list) else []
            if data_rows:
                first = data_rows[0] if isinstance(data_rows[0], dict) else {}
                price_obj = first.get("price") if isinstance(first, dict) else {}
                price_id = str((price_obj or {}).get("id") or "").strip() if isinstance(price_obj, dict) else ""
                plan_tier = self._plan_tier_for_price_id(price_id)

        self.store.upsert_subscription(
            email=email,
            stripe_customer_id=customer_id,
            stripe_subscription_id=sub_id,
            status=status,
            plan_tier=plan_tier,
            current_period_end=period_end,
            raw_payload=sub,
        )
        if not self.store.subscription_active(email):
            self.store.revoke_sessions_for_email(email)
        return {
            "email": email,
            "status": status,
            "plan_tier": plan_tier,
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
        plan = self._ensure_access_plan(normalized)
        code = self.store.create_login_code(
            normalized,
            ttl_seconds=self.config.login_code_ttl_seconds,
            cooldown_seconds=self.config.login_code_cooldown_seconds,
        )

        response: Dict[str, Any] = {
            "ok": True,
            "expires_in_seconds": int(self.config.login_code_ttl_seconds),
            "plan_tier": str(plan.get("tier") or PLAN_FREE),
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
        self._ensure_access_plan(normalized)
        ok = self.store.verify_login_code(normalized, str(code or "").strip())
        if not ok:
            raise PermissionError("Invalid or expired login code")
        return self.store.create_session(
            normalized,
            ttl_seconds=self.config.session_ttl_seconds,
        )

    def create_session_for_email(self, email: str) -> str:
        normalized = normalize_email(email)
        self._ensure_access_plan(normalized)
        return self.store.create_session(
            normalized,
            ttl_seconds=self.config.session_ttl_seconds,
        )

    def session_email(self, token: str) -> Optional[str]:
        email = self.store.session_email(token)
        if not email:
            return None
        plan = self.account_plan(email)
        if not plan.get("active"):
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

    def _ensure_access_plan(self, email: str) -> Dict[str, Any]:
        normalized = normalize_email(email)
        if self.store.subscription_active(normalized):
            return self.account_plan(normalized)
        if not self.config.allow_free_tier:
            raise PermissionError("No active subscription found for this email")
        existing = self.store.subscription_for_email(normalized) or {}
        self.store.upsert_subscription(
            email=normalized,
            stripe_customer_id=existing.get("stripe_customer_id"),
            stripe_subscription_id=None,
            status="free",
            plan_tier=PLAN_FREE,
            current_period_end=None,
            raw_payload={
                "source": "free-tier",
                "previous_status": existing.get("status"),
                "upgraded_at": _utc_now_iso(),
            },
        )
        return self.account_plan(normalized)

    def account_plan(self, email: str | None) -> Dict[str, Any]:
        normalized = normalize_email(email) if email else ""
        info = self.store.subscription_for_email(normalized) if normalized else None

        if not info:
            tier = PLAN_FREE
            status = "free"
            active = bool(self.config.allow_free_tier)
        else:
            status = str(info.get("status") or "free").strip().lower() or "free"
            stored_tier = normalize_plan_tier(str(info.get("plan_tier") or ""), default=PLAN_FREE)
            if status in ACTIVE_SUBSCRIPTION_STATUSES:
                tier = stored_tier if stored_tier in PAID_PLAN_TIERS else PLAN_PRO
            elif status == "free":
                tier = PLAN_FREE
            elif self.config.allow_free_tier:
                tier = PLAN_FREE
                status = "free"
            else:
                tier = stored_tier
            active = self.store.subscription_active(normalized)
            if not active and self.config.allow_free_tier and tier == PLAN_FREE:
                active = True

        entitlements = plan_entitlements(tier)
        entitlements["status"] = status
        entitlements["active"] = bool(active)
        entitlements["paid"] = tier in PAID_PLAN_TIERS
        entitlements["email"] = normalized or None
        return entitlements

    def plan_catalog(self) -> list[dict]:
        paid_available = set(self.checkout_enabled_tiers())
        catalog: list[dict] = []
        for tier in [PLAN_FREE, PLAN_PRO, PLAN_ELITE]:
            row = plan_entitlements(tier)
            row["checkout_enabled"] = tier in paid_available
            row["paid"] = tier in PAID_PLAN_TIERS
            catalog.append(row)
        return catalog
