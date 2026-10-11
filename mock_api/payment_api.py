"""Small fake payment API (stdlib only) so the project runs offline.

    GET /health
    GET /payments?page=1&page_size=250

The pipeline starts it automatically. To run it on its own:
    python -m mock_api.payment_api --port 8765
"""
from __future__ import annotations

import argparse
import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

MAX_PAGE_SIZE = 500


def _make_handler(payments: list[dict]):
    class PaymentAPIHandler(BaseHTTPRequestHandler):
        def _send(self, status: int, body: dict) -> None:
            payload = json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802 (required name)
            url = urlparse(self.path)
            if url.path == "/health":
                return self._send(200, {"status": "ok"})
            if url.path != "/payments":
                return self._send(404, {"error": "not found"})

            query = parse_qs(url.query)
            try:
                page = int(query.get("page", ["1"])[0])
                page_size = int(query.get("page_size", ["100"])[0])
            except ValueError:
                return self._send(400, {"error": "page and page_size must be integers"})
            if page < 1 or not 1 <= page_size <= MAX_PAGE_SIZE:
                return self._send(400, {"error": f"page >= 1 and 1 <= page_size <= {MAX_PAGE_SIZE}"})

            total = len(payments)
            start = (page - 1) * page_size
            return self._send(200, {
                "data": payments[start:start + page_size],
                "page": page,
                "page_size": page_size,
                "total_records": total,
                "total_pages": max(1, math.ceil(total / page_size)),
            })

        def log_message(self, *args) -> None:  # keep console output clean
            pass

    return PaymentAPIHandler


def make_server(payments_file: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    payments = json.loads(Path(payments_file).read_text(encoding="utf-8"))
    return ThreadingHTTPServer((host, port), _make_handler(payments))


def start_in_background(payments_file: Path, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    server = make_server(payments_file, host, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    from pipeline.config import Settings

    parser = argparse.ArgumentParser(description="Run the mock Payment API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    srv = make_server(Settings().api_data_file, args.host, args.port)
    print(f"Mock Payment API on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
