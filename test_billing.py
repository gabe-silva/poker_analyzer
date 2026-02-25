#!/usr/bin/env python3
"""Tests for billing/auth persistence utilities."""

from __future__ import annotations

import time
from pathlib import Path
from tempfile import TemporaryDirectory

from trainer.billing import BillingConfig, BillingService, BillingStore


def _config_for_tests() -> BillingConfig:
    return BillingConfig(
        stripe_secret_key="",
        stripe_webhook_secret="",
        stripe_price_id_pro="",
        stripe_price_id_elite="",
        session_ttl_seconds=3600,
        login_code_ttl_seconds=300,
        login_code_cooldown_seconds=0,
        mailgun_api_key="",
        mailgun_domain="",
        mailgun_from_email="",
        allow_free_tier=True,
        expose_login_codes=True,
    )


def test_billing_store_login_codes_and_sessions():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "billing.db"
        store = BillingStore(db_path=db_path, secret_key="test-secret")

        now = int(time.time())
        store.upsert_subscription(
            email="test@example.com",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
            status="active",
            plan_tier="pro",
            current_period_end=now + 3600,
            raw_payload={"id": "sub_123"},
        )
        assert store.subscription_active("test@example.com")

        code = store.create_login_code(
            "test@example.com",
            ttl_seconds=300,
            cooldown_seconds=0,
        )
        assert len(code) == 6
        assert store.verify_login_code("test@example.com", code)

        token = store.create_session("test@example.com", ttl_seconds=300)
        assert token
        assert store.session_email(token) == "test@example.com"
        store.revoke_session(token)
        assert store.session_email(token) is None


def test_billing_service_debug_login_code_path():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "billing.db"
        store = BillingStore(db_path=db_path, secret_key="test-secret")
        service = BillingService(config=_config_for_tests(), store=store)
        now = int(time.time())
        store.upsert_subscription(
            email="paid@example.com",
            stripe_customer_id=None,
            stripe_subscription_id=None,
            status="active",
            plan_tier="pro",
            current_period_end=now + 3600,
            raw_payload={},
        )

        request_result = service.request_login_code("paid@example.com")
        assert request_result["ok"] is True
        assert "debug_code" in request_result

        token = service.verify_login_code("paid@example.com", request_result["debug_code"])
        assert token
        assert service.session_email(token) == "paid@example.com"


def test_billing_service_creates_free_plan_login_when_missing_subscription():
    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "billing.db"
        store = BillingStore(db_path=db_path, secret_key="test-secret")
        service = BillingService(config=_config_for_tests(), store=store)

        request_result = service.request_login_code("freeuser@example.com")
        assert request_result["ok"] is True
        assert request_result["plan_tier"] == "free"
        code = request_result["debug_code"]
        token = service.verify_login_code("freeuser@example.com", code)
        assert token
        assert service.session_email(token) == "freeuser@example.com"
        plan = service.account_plan("freeuser@example.com")
        assert plan["tier"] == "free"
        assert plan["active"] is True
