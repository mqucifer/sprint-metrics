"""Scrape HTTP server for the sprint-metrics package."""

from __future__ import annotations

import http.server
import threading

from sprint_metrics.card import _load_cards
from sprint_metrics.metrics import _load_wip_limits
from sprint_metrics.report import format_prometheus_report


def serve_metrics(
    cards_path: str,
    wip_limits_path: str | None = None,
    escalations: int = 0,
    port: int = 9100,
) -> int:
    """Start an HTTP server that serves the current sprint metrics at /metrics.

    The cards file is re-read on every request so that changes to the board are
    reflected without a restart. Returns the port the server is listening on.
    """

    class MetricsHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/metrics":
                self.send_response(404)
                self.end_headers()
                return

            try:
                with open(cards_path) as f:
                    cards = _load_cards(f.read())
                wip_limits = None
                if wip_limits_path is not None:
                    with open(wip_limits_path) as f:
                        wip_limits = _load_wip_limits(f.read())
            except (TypeError, ValueError, OSError) as exc:
                error_body = f"sprint-metrics: {exc}"
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(error_body)))
                self.end_headers()
                self.wfile.write(error_body.encode())
                return

            body = format_prometheus_report(cards, wip_limits, escalations)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body.encode())

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), MetricsHandler)
    actual_port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return actual_port
