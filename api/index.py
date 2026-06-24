from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server import AppHandler  # noqa: E402


class handler(AppHandler):
    def route(self) -> None:
        self._restore_vercel_path()
        return super().route()

    def _restore_vercel_path(self) -> None:
        parsed = urlsplit(self.path)
        params = parse_qs(parsed.query, keep_blank_values=True)
        values = params.pop("__path", None)
        if not values:
            return
        target = values[0] or "/"
        if not target.startswith("/"):
            target = "/" + target
        query = urlencode(params, doseq=True)
        self.path = target + (f"?{query}" if query else "")
