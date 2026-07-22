import json
import logging
import threading
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from plugins.BaseFrontend import BaseFrontend, FrontendCapabilities
from state_machine.conversation_phases import PHASE_APPROVING_REQUEST

logger = logging.getLogger("WebUI")

WWW_DIR = Path("C:/Users/Parth/Desktop/SecondBrain/Database/www")
WWW_DIR.mkdir(parents=True, exist_ok=True)

class WebUIFrontend(BaseFrontend):
    name = "web"
    description = "Premium Web UI frontend with drag-and-drop."
    capabilities = FrontendCapabilities(
        supports_attachments_in=True,
        supports_proactive_push=True,
    )

    def __init__(self, shutdown_fn=None, shutdown_event=None):
        super().__init__()
        self.shutdown_fn = shutdown_fn
        self.shutdown_event = shutdown_event or threading.Event()
        self.message_queues = defaultdict(list)
        self.server = None

    def session_key(self, _ctx=None) -> str:
        return "default"

    def start(self) -> None:
        key = self.session_key(None)
        logger.info("Web UI starting on http://127.0.0.1:8000")
        
        try:
            notice = self.runtime.restore_last_active(key)
            if notice:
                self.render_messages(key, [notice])
        except Exception:
            logger.exception("WebUI restore_last_active failed")

        class RequestHandler(BaseHTTPRequestHandler):
            def do_GET(req):
                parsed = urlparse(req.path)
                if parsed.path == "/api/poll":
                    req.send_response(200)
                    req.send_header("Content-type", "application/json")
                    req.end_headers()
                    msgs = []
                    if self.message_queues[key]:
                        msgs = self.message_queues[key][:]
                        self.message_queues[key].clear()
                    req.wfile.write(json.dumps({"messages": msgs}).encode())
                    return
                
                if parsed.path == "/favicon.ico":
                    req.send_response(204)
                    req.end_headers()
                    return
                
                # Serve static files
                if parsed.path == "/":
                    file_path = WWW_DIR / "index.html"
                else:
                    file_path = WWW_DIR / parsed.path.lstrip("/")
                
                if not file_path.exists():
                    req.send_response(404)
                    req.end_headers()
                    return
                
                req.send_response(200)
                if file_path.suffix == ".html":
                    req.send_header("Content-type", "text/html")
                elif file_path.suffix == ".css":
                    req.send_header("Content-type", "text/css")
                elif file_path.suffix == ".js":
                    req.send_header("Content-type", "application/javascript")
                req.end_headers()
                req.wfile.write(file_path.read_bytes())

            def do_POST(req):
                parsed = urlparse(req.path)
                if parsed.path == "/api/chat":
                    length = int(req.headers.get("Content-Length", 0))
                    body = json.loads(req.rfile.read(length))
                    text = body.get("text", "").strip()
                    
                    if text:
                        if text.startswith("/attach "):
                            _, _, path = text.partition(" ")
                            threading.Thread(target=self.submit_attachment, args=(key, path.strip()), daemon=True).start()
                        else:
                            if self.has_pending_approval(key):
                                # Approval mode
                                approved = text.lower() in ["y", "yes", "approve", "1", "true"]
                                ok = self.resolve_next_approval(key, approved, self.name)
                                self.render_messages(key, ["Approval granted." if ok and approved else "Approval denied." if ok else "No pending approvals."])
                            else:
                                threading.Thread(target=self.submit_text, args=(key, text), daemon=True).start()
                                
                    req.send_response(200)
                    req.send_header("Content-type", "application/json")
                    req.end_headers()
                    req.wfile.write(json.dumps({"status": "ok"}).encode())

            def log_message(self, format, *args):
                pass # suppress HTTP logs

        self.server = HTTPServer(("127.0.0.1", 8000), RequestHandler)
        self.server.serve_forever()

    def stop(self) -> None:
        self.shutdown_event.set()
        if self.server:
            self.server.shutdown()
        self.unbind()

    def _queue_msg(self, session_key: str, msg: str, is_html=False):
        self.message_queues[session_key].append({"text": msg, "html": is_html})

    def render_messages(self, _session_key: str, messages: list[str]) -> None:
        for msg in messages:
            if msg:
                self._queue_msg(_session_key, msg)

    def render_attachments(self, _session_key: str, paths: list[str]) -> None:
        for path in paths:
            self._queue_msg(_session_key, f"[Attachment Processed] {path}")

    def render_form_field(self, _session_key: str, form: dict) -> None:
        field = form.get("field") or {}
        display = form.get("display") or {}
        prompt = display.get("prompt") or field.get("prompt") or field.get("name") or "Input required"
        self._queue_msg(_session_key, f"<b>[Form]</b> {prompt}", is_html=True)

    def render_approval_request(self, _session_key: str, req) -> None:
        body = getattr(req, "body", "")
        self._queue_msg(_session_key, f"<b>Approval Requested:</b> {getattr(req, 'title', 'Approval')}<br>{body}<br><i>Reply 'yes' or 'no'</i>", is_html=True)

    def render_buttons(self, _session_key: str, buttons: list[dict]) -> None:
        for i, button in enumerate(buttons, 1):
            label = button.get("label") or button.get("text") or button.get("value") or "Option"
            self._queue_msg(_session_key, f"{i}. {label}")

    def render_error(self, _session_key: str, error: dict) -> None:
        self._queue_msg(_session_key, f"<span style='color:red;'>[Error] {(error or {}).get('message') or error}</span>", is_html=True)

    def render_tool_status(self, _session_key: str, payload: dict) -> None:
        name = payload.get("tool_name") or payload.get("command_name") or "call"
        if payload.get("status") == "started":
            self._queue_msg(_session_key, f"<i>Running tool: {name}...</i>", is_html=True)
        elif payload.get("status") == "finished":
            icon = "✅" if payload.get("ok") else "❌"
            self._queue_msg(_session_key, f"<i>{icon} Finished tool: {name}</i>", is_html=True)

    def _live_session_keys(self) -> list[str]:
        return [self.session_key(None)]
