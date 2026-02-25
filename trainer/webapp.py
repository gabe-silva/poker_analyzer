"""Production WSGI app for the poker trainer SaaS deployment."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Set
from urllib.parse import quote

from flask import Flask, g, jsonify, make_response, redirect, request, send_from_directory

from trainer.billing import BillingConfig, BillingService, BillingStore
from trainer.service import TrainerService

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_ROOT = Path(__file__).resolve().parent / "web"

PROTECTED_PAGE_PATHS = {
    "/",
    "/setup",
    "/setup.html",
    "/trainer",
    "/trainer.html",
    "/play",
    "/play.html",
    "/standings",
    "/standings.html",
}

PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/status",
    "/api/auth/request-code",
    "/api/auth/verify-code",
    "/api/billing/create-checkout-session",
    "/api/billing/webhook",
}


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except ValueError:
        return int(default)


def _split_csv(value: str) -> Set[str]:
    return {part.strip().lower() for part in str(value or "").split(",") if part.strip()}


def _resolve_db_path(raw: str) -> Path:
    raw_value = str(raw or "").strip()
    if not raw_value:
        return PROJECT_ROOT / "trainer" / "data" / "trainer.db"
    candidate = Path(raw_value)
    if candidate.is_absolute():
        return candidate
    return (PROJECT_ROOT / candidate).resolve()


def _is_subpath(child: Path, parent: Path) -> bool:
    child_parts = child.resolve().parts
    parent_parts = parent.resolve().parts
    return len(child_parts) >= len(parent_parts) and child_parts[: len(parent_parts)] == parent_parts


def _safe_next_path(raw_next: str) -> str:
    nxt = str(raw_next or "").strip()
    if not nxt:
        return "/setup.html"
    if not nxt.startswith("/"):
        return "/setup.html"
    if nxt.startswith("//"):
        return "/setup.html"
    return nxt


def _api_error(message: str, status: int = 400):
    return jsonify({"error": str(message)}), int(status)


@dataclass(frozen=True)
class RuntimeConfig:
    env: str
    db_path: Path
    require_auth: bool
    allowed_hosts: Set[str]
    force_https: bool
    public_base_url: str
    cookie_name: str
    cookie_secure: bool
    session_ttl_seconds: int
    secret_key: str


def _load_runtime_config() -> RuntimeConfig:
    env = str(os.getenv("TRAINER_ENV", "development")).strip().lower()
    secret_key = str(os.getenv("TRAINER_SECRET_KEY", "")).strip()
    if not secret_key:
        if env == "production":
            raise RuntimeError("TRAINER_SECRET_KEY is required in production")
        secret_key = secrets.token_urlsafe(48)

    session_ttl_days = _env_int("TRAINER_SESSION_TTL_DAYS", 30)
    db_path = _resolve_db_path(os.getenv("TRAINER_DB_PATH", "trainer/data/trainer.db"))
    return RuntimeConfig(
        env=env,
        db_path=db_path,
        require_auth=_env_bool("TRAINER_REQUIRE_AUTH", env == "production"),
        allowed_hosts=_split_csv(os.getenv("TRAINER_ALLOWED_HOSTS", "")),
        force_https=_env_bool("TRAINER_FORCE_HTTPS", env == "production"),
        public_base_url=str(os.getenv("TRAINER_PUBLIC_BASE_URL", "")).strip().rstrip("/"),
        cookie_name=str(os.getenv("TRAINER_SESSION_COOKIE_NAME", "poker_trainer_session")).strip(),
        cookie_secure=_env_bool("TRAINER_COOKIE_SECURE", env == "production"),
        session_ttl_seconds=max(3600, session_ttl_days * 24 * 60 * 60),
        secret_key=secret_key,
    )


def _load_billing_config(runtime: RuntimeConfig) -> BillingConfig:
    return BillingConfig(
        stripe_secret_key=str(os.getenv("STRIPE_SECRET_KEY", "")).strip(),
        stripe_webhook_secret=str(os.getenv("STRIPE_WEBHOOK_SECRET", "")).strip(),
        stripe_price_id=str(os.getenv("STRIPE_PRICE_ID", "")).strip(),
        session_ttl_seconds=runtime.session_ttl_seconds,
        login_code_ttl_seconds=max(120, _env_int("TRAINER_LOGIN_CODE_TTL_SECONDS", 600)),
        login_code_cooldown_seconds=max(0, _env_int("TRAINER_LOGIN_CODE_COOLDOWN_SECONDS", 60)),
        mailgun_api_key=str(os.getenv("MAILGUN_API_KEY", "")).strip(),
        mailgun_domain=str(os.getenv("MAILGUN_DOMAIN", "")).strip(),
        mailgun_from_email=str(
            os.getenv("MAILGUN_FROM_EMAIL", "Poker Trainer <noreply@localhost>")
        ).strip(),
        expose_login_codes=_env_bool(
            "TRAINER_EXPOSE_LOGIN_CODES",
            runtime.env != "production",
        ),
    )


def create_app() -> Flask:
    runtime = _load_runtime_config()
    billing_config = _load_billing_config(runtime)

    service = TrainerService(db_path=runtime.db_path)
    billing_store = BillingStore(db_path=runtime.db_path, secret_key=runtime.secret_key)
    billing = BillingService(config=billing_config, store=billing_store)

    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    def _base_url() -> str:
        if runtime.public_base_url:
            return runtime.public_base_url
        proto = str(request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
        host = str(request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip()
        return f"{proto}://{host}"

    def _set_session_cookie(resp, token: str):
        resp.set_cookie(
            runtime.cookie_name,
            token,
            max_age=runtime.session_ttl_seconds,
            httponly=True,
            secure=runtime.cookie_secure,
            samesite="Lax",
            path="/",
        )
        return resp

    def _clear_session_cookie(resp):
        resp.delete_cookie(runtime.cookie_name, path="/")
        return resp

    def _requires_auth(path: str) -> bool:
        if not runtime.require_auth:
            return False
        if path in PROTECTED_PAGE_PATHS:
            return True
        if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
            return True
        return False

    @app.before_request
    def _before_request():
        host = str(request.headers.get("X-Forwarded-Host") or request.host).split(",")[0].strip().lower()
        host_no_port = host.split(":")[0]
        if runtime.allowed_hosts and host_no_port not in runtime.allowed_hosts:
            return _api_error("Host is not allowed", status=400)

        if runtime.force_https:
            proto = (
                str(request.headers.get("X-Forwarded-Proto") or request.scheme)
                .split(",")[0]
                .strip()
                .lower()
            )
            if proto != "https":
                target = f"https://{request.host}{request.full_path}"
                if target.endswith("?"):
                    target = target[:-1]
                return redirect(target, code=301)

        if not _requires_auth(request.path):
            return None

        token = str(request.cookies.get(runtime.cookie_name, "")).strip()
        email = billing.session_email(token) if token else None
        if not email:
            if request.path.startswith("/api/"):
                return _api_error("Authentication required", status=401)
            next_url = request.full_path
            if next_url.endswith("?"):
                next_url = next_url[:-1]
            return redirect(f"/login?next={quote(next_url, safe='')}")
        g.current_user_email = email
        return None

    @app.after_request
    def _after_request(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        return resp

    @app.get("/api/health")
    @app.get("/healthz")
    def health():
        return jsonify({"ok": True})

    @app.get("/login")
    @app.get("/login.html")
    def login_page():
        return send_from_directory(str(WEB_ROOT), "login.html")

    @app.get("/billing/cancel")
    def billing_cancel():
        return redirect("/login?billing=cancelled")

    @app.get("/billing/success")
    def billing_success():
        session_id = str(request.args.get("session_id", "")).strip()
        next_path = _safe_next_path(str(request.args.get("next", "/setup.html")))
        if not session_id:
            return redirect("/login?error=missing_session")
        try:
            sync = billing.sync_checkout_session(session_id)
            token = billing.create_session_for_email(sync["email"])
        except Exception:  # noqa: BLE001
            return redirect("/login?error=payment_not_verified")
        resp = make_response(redirect(next_path))
        return _set_session_cookie(resp, token)

    @app.get("/api/auth/status")
    def auth_status():
        token = str(request.cookies.get(runtime.cookie_name, "")).strip()
        email = billing.session_email(token) if token else None
        return jsonify(
            {
                "authenticated": bool(email),
                "email": email,
                "billing_enabled": billing.enabled,
            }
        )

    @app.post("/api/auth/request-code")
    def auth_request_code():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip()
        try:
            result = billing.request_login_code(email)
            return jsonify(result)
        except PermissionError as exc:
            return _api_error(str(exc), status=403)
        except ValueError as exc:
            return _api_error(str(exc), status=400)
        except RuntimeError as exc:
            return _api_error(str(exc), status=500)

    @app.post("/api/auth/verify-code")
    def auth_verify_code():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip()
        code = str(payload.get("code", "")).strip()
        try:
            token = billing.verify_login_code(email, code)
        except PermissionError as exc:
            return _api_error(str(exc), status=403)
        except ValueError as exc:
            return _api_error(str(exc), status=400)
        resp = make_response(jsonify({"ok": True}))
        return _set_session_cookie(resp, token)

    @app.post("/api/auth/logout")
    def auth_logout():
        token = str(request.cookies.get(runtime.cookie_name, "")).strip()
        if token:
            billing.logout(token)
        resp = make_response(jsonify({"ok": True}))
        return _clear_session_cookie(resp)

    @app.post("/api/billing/create-checkout-session")
    def create_checkout_session():
        payload = request.get_json(silent=True) or {}
        email = str(payload.get("email", "")).strip()
        try:
            session = billing.create_checkout_session(
                email=email,
                success_url=f"{_base_url()}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{_base_url()}/billing/cancel",
            )
            return jsonify(session)
        except ValueError as exc:
            return _api_error(str(exc), status=400)
        except RuntimeError as exc:
            return _api_error(str(exc), status=500)

    @app.post("/api/billing/create-portal-session")
    def create_portal_session():
        email = str(getattr(g, "current_user_email", "")).strip()
        if not email:
            return _api_error("Authentication required", status=401)
        try:
            payload = billing.create_portal_session(
                email=email,
                return_url=f"{_base_url()}/setup.html",
            )
            return jsonify(payload)
        except ValueError as exc:
            return _api_error(str(exc), status=400)
        except RuntimeError as exc:
            return _api_error(str(exc), status=500)

    @app.post("/api/billing/webhook")
    def billing_webhook():
        signature = str(request.headers.get("Stripe-Signature", "")).strip()
        payload = request.get_data(cache=False, as_text=False)
        try:
            event = billing.handle_webhook(payload=payload, signature_header=signature)
            return jsonify({"received": True, **event})
        except Exception as exc:  # noqa: BLE001
            return _api_error(str(exc), status=400)

    @app.get("/api/config")
    def api_config():
        return jsonify(service.app_config())

    @app.get("/api/scenario")
    def api_scenario():
        scenario_id = str(request.args.get("scenario_id", "")).strip()
        if not scenario_id:
            return _api_error("scenario_id is required", status=400)
        try:
            return jsonify(service.get_scenario(scenario_id))
        except Exception as exc:  # noqa: BLE001
            return _api_error(str(exc), status=400)

    @app.get("/api/progress")
    def api_progress():
        return jsonify(service.progress())

    @app.get("/api/opponent_profile")
    def api_opponent_profile():
        name = str(request.args.get("name", "")).strip()
        if not name:
            return _api_error("name is required", status=400)
        try:
            return jsonify(service.analyzer_profile(name))
        except Exception as exc:  # noqa: BLE001
            return _api_error(str(exc), status=400)

    @app.get("/api/live/state")
    def api_live_state():
        session_id = str(request.args.get("session_id", "")).strip()
        if not session_id:
            return _api_error("session_id is required", status=400)
        try:
            return jsonify(service.live_state(session_id))
        except Exception as exc:  # noqa: BLE001
            return _api_error(str(exc), status=400)

    def _json_post(payload_handler):
        payload = request.get_json(silent=True) or {}
        try:
            return jsonify(payload_handler(payload))
        except Exception as exc:  # noqa: BLE001
            return _api_error(str(exc), status=400)

    @app.post("/api/generate")
    def api_generate():
        return _json_post(service.generate)

    @app.post("/api/evaluate")
    def api_evaluate():
        return _json_post(service.evaluate)

    @app.post("/api/clear_saved_hands")
    def api_clear_saved():
        return _json_post(lambda _payload: service.clear_saved_hands())

    @app.post("/api/live/start")
    def api_live_start():
        return _json_post(service.live_start)

    @app.post("/api/live/action")
    def api_live_action():
        return _json_post(service.live_action)

    @app.post("/api/live/new_hand")
    def api_live_new_hand():
        return _json_post(service.live_new_hand)

    def _serve_page(filename: str):
        return send_from_directory(str(WEB_ROOT), filename)

    @app.get("/")
    @app.get("/setup")
    @app.get("/setup.html")
    def setup_page():
        return _serve_page("setup.html")

    @app.get("/trainer")
    @app.get("/trainer.html")
    def trainer_page():
        return _serve_page("trainer.html")

    @app.get("/play")
    @app.get("/play.html")
    def play_page():
        return _serve_page("play.html")

    @app.get("/standings")
    @app.get("/standings.html")
    def standings_page():
        return _serve_page("standings.html")

    @app.get("/<path:filename>")
    def static_files(filename: str):
        candidate = (WEB_ROOT / filename).resolve()
        if not _is_subpath(candidate, WEB_ROOT):
            return _api_error("Not found", status=404)
        if not candidate.exists() or not candidate.is_file():
            return _api_error("Not found", status=404)
        if candidate.suffix.lower() not in {".html", ".css", ".js", ".png", ".svg", ".ico"}:
            return _api_error("Not found", status=404)
        return send_from_directory(str(WEB_ROOT), filename)

    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return _api_error("Not found", status=404)
        return redirect("/login")

    return app
