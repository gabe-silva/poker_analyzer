"""HTTP server for the poker trainer UI and JSON API."""

from __future__ import annotations

import json
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from trainer.service import TrainerService


class TrainerRequestHandler(SimpleHTTPRequestHandler):
    """Serve static trainer UI + simple JSON API routes."""

    def __init__(
        self,
        *args: Any,
        service: TrainerService,
        directory: str,
        **kwargs: Any,
    ):
        self.service = service
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, payload: Any, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _read_multipart_files(self) -> list[tuple[str, bytes]]:
        content_type = str(self.headers.get("Content-Type", "")).strip()
        if "multipart/form-data" not in content_type.lower():
            return []
        boundary = ""
        for part in content_type.split(";"):
            token = part.strip()
            if token.lower().startswith("boundary="):
                boundary = token.split("=", 1)[1].strip().strip('"')
                break
        if not boundary:
            return []
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return []
        raw = self.rfile.read(length)
        if not raw:
            return []

        delimiter = f"--{boundary}".encode("utf-8")
        out: list[tuple[str, bytes]] = []
        for part in raw.split(delimiter):
            chunk = part.strip(b"\r\n")
            if not chunk or chunk == b"--":
                continue
            if chunk.endswith(b"--"):
                chunk = chunk[:-2]
            header_blob, marker, body = chunk.partition(b"\r\n\r\n")
            if not marker:
                continue
            headers_text = header_blob.decode("utf-8", errors="ignore")
            disposition = ""
            for header_line in headers_text.split("\r\n"):
                if header_line.lower().startswith("content-disposition:"):
                    disposition = header_line
                    break
            if 'name="files"' not in disposition:
                continue
            filename = ""
            for token in disposition.split(";"):
                token = token.strip()
                if token.startswith("filename="):
                    filename = token.split("=", 1)[1].strip().strip('"')
                    break
            if body.endswith(b"\r\n"):
                body = body[:-2]
            out.append((filename, bytes(body)))
        return out

    def log_message(self, format: str, *args: Any) -> None:
        # Keep terminal output concise while running drills.
        return super().log_message(format, *args)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/api/config":
            self._send_json(self.service.app_config())
            return
        if path == "/api/scenario":
            scenario_id = (query.get("scenario_id") or [None])[0]
            if not scenario_id:
                self._send_json({"error": "scenario_id is required"}, status=400)
                return
            self._send_json(self.service.get_scenario(scenario_id))
            return
        if path == "/api/opponent_profile":
            name = (query.get("name") or [None])[0]
            if not name:
                self._send_json({"error": "name is required"}, status=400)
                return
            self._send_json(self.service.analyzer_profile(str(name)))
            return
        if path == "/api/opponent/compare":
            self._send_json({"error": "Use POST /api/opponent/compare"}, status=405)
            return
        if path == "/api/hands/players":
            self._send_json(self.service.hands_players())
            return
        if path == "/api/live/state":
            session_id = (query.get("session_id") or [None])[0]
            if not session_id:
                self._send_json({"error": "session_id is required"}, status=400)
                return
            self._send_json(self.service.live_state(str(session_id)))
            return
        if path == "/api/health":
            self._send_json({"ok": True})
            return
        if path in {"/", "/index"}:
            self.path = "/index.html"
        elif path == "/setup":
            self.path = "/setup.html"
        elif path == "/trainer":
            self.path = "/trainer.html"
        elif path == "/play":
            self.path = "/play.html"
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/hands/upload":
                self._send_json(self.service.upload_hands(self._read_multipart_files()), status=200)
                return
            payload = self._read_json_body()
            if path == "/api/opponent/compare":
                groups = payload.get("groups")
                if not isinstance(groups, list) or not groups:
                    self._send_json({"error": "groups is required and must be a list"}, status=400)
                    return
                out = []
                for idx, group in enumerate(groups):
                    if not isinstance(group, dict):
                        self._send_json({"error": "Each group must be an object"}, status=400)
                        return
                    usernames = group.get("usernames")
                    aliases = [str(v).strip() for v in (usernames or []) if str(v).strip()]
                    if not aliases:
                        self._send_json({"error": f"Group {idx + 1} requires at least one username"}, status=400)
                        return
                    prof = self.service.analyzer_profile(",".join(aliases))
                    prof["group_label"] = str(group.get("label", f"Player {idx + 1}")).strip() or f"Player {idx + 1}"
                    out.append(prof)
                self._send_json({"profiles": out}, status=200)
                return
            if path == "/api/generate":
                self._send_json(self.service.generate(payload), status=200)
                return
            if path == "/api/evaluate":
                self._send_json(self.service.evaluate(payload), status=200)
                return
            if path == "/api/clear_saved_hands":
                self._send_json(self.service.clear_saved_hands(), status=200)
                return
            if path == "/api/live/start":
                self._send_json(self.service.live_start(payload), status=200)
                return
            if path == "/api/live/action":
                self._send_json(self.service.live_action(payload), status=200)
                return
            if path == "/api/live/new_hand":
                self._send_json(self.service.live_new_hand(payload), status=200)
                return
            self._send_json({"error": f"Unknown endpoint: {path}"}, status=404)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=400)


def run_server(
    service: TrainerService,
    host: str = "127.0.0.1",
    port: int = 8787,
    open_browser: bool = True,
) -> None:
    """Run trainer web server until interrupted."""
    web_root = Path(__file__).resolve().parent / "web"
    handler = partial(TrainerRequestHandler, service=service, directory=str(web_root))
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{port}"
    print(f"Trainer running at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
