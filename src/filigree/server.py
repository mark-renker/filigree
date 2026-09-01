"""Local playground server. Standard library only.

    python -m filigree.server --port 8787 --web ./web

Endpoints:
    GET  /                  -> web/index.html (and all static files under web/)
    POST /api/compile       {"source": "..."}  -> Score.to_json() plus diagnostics
    POST /api/midi          {"source": "..."}  -> audio/midi bytes
    POST /api/play          {"source": "...", "port": null} -> realtime playback (best effort)
    GET  /api/ports         -> {"ports": [...]}
    GET  /api/health        -> {"ok": true, "version": "..."}
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import threading
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from . import __version__, compile_source
from .errors import FiligreeError

WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "web")

_play_lock = threading.Lock()
_play_thread: threading.Thread | None = None


def _diag(exc: BaseException) -> dict:
    if isinstance(exc, FiligreeError):
        return {
            "ok": False,
            "error": {
                "message": exc.message,
                "line": exc.line,
                "col": exc.col,
                "token": exc.token,
                "suggestion": exc.suggestion,
                "kind": type(exc).__name__,
            },
        }
    return {
        "ok": False,
        "error": {
            "message": f"{type(exc).__name__}: {exc}",
            "line": 0,
            "col": 0,
            "token": "",
            "suggestion": "",
            "kind": "InternalError",
            "traceback": traceback.format_exc(limit=8),
        },
    }


class Handler(SimpleHTTPRequestHandler):
    web_dir = WEB_DIR

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=self.web_dir, **kw)

    # -- plumbing ---------------------------------------------------------
    def log_message(self, fmt, *args):  # quieter
        if os.environ.get("FILIGREE_VERBOSE"):
            super().log_message(fmt, *args)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def end_headers(self):
        if self.path.endswith((".js", ".css", ".html", ".json", ".fil")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    # -- routes -----------------------------------------------------------
    def do_GET(self):  # noqa: N802
        if self.path.startswith("/api/health"):
            return self._json({"ok": True, "version": __version__})
        if self.path.startswith("/api/ports"):
            try:
                from .realtime import list_ports

                return self._json({"ok": True, "ports": list_ports()})
            except Exception as exc:  # pragma: no cover
                return self._json({"ok": True, "ports": [], "note": str(exc)})
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        try:
            if self.path.startswith("/api/compile"):
                return self._compile()
            if self.path.startswith("/api/midi"):
                return self._midi()
            if self.path.startswith("/api/play"):
                return self._play()
            return self._json({"ok": False, "error": {"message": "no such route"}}, 404)
        except Exception as exc:  # pragma: no cover
            return self._json(_diag(exc), 200)

    def _compile(self):
        src = self._body().get("source", "")
        try:
            score = compile_source(src, "playground.fil")
        except Exception as exc:
            return self._json(_diag(exc))
        payload = score.to_json()
        payload["ok"] = True
        payload["version"] = __version__
        return self._json(payload)

    def _midi(self):
        from .mpe import MpeOptions, render_midifile

        body = self._body()
        try:
            score = compile_source(body.get("source", ""), "playground.fil")
            mf = render_midifile(score, MpeOptions(
                bend_range=score.bend_range, ppq=score.ppq, grid_ms=score.grid_ms))
        except Exception as exc:
            return self._json(_diag(exc))
        buf = io.BytesIO()
        mf.save(file=buf)
        data = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "audio/midi")
        self.send_header("Content-Disposition", 'attachment; filename="filigree.mid"')
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def _play(self):
        global _play_thread
        body = self._body()
        try:
            score = compile_source(body.get("source", ""), "playground.fil")
        except Exception as exc:
            return self._json(_diag(exc))
        try:
            from .realtime import play
        except Exception as exc:
            return self._json({"ok": False, "error": {"message": f"realtime unavailable: {exc}"}})

        def run():
            with _play_lock:
                try:
                    play(score, body.get("port"))
                except Exception:
                    pass

        _play_thread = threading.Thread(target=run, daemon=True)
        _play_thread.start()
        return self._json({"ok": True, "playing": True})


def serve(port: int = 8787, web: str | None = None, open_browser: bool = False) -> None:
    Handler.web_dir = os.path.abspath(web or WEB_DIR)
    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    url = f"http://localhost:{port}/"
    print(f"filigree playground → {url}\n  serving {Handler.web_dir}", flush=True)
    if open_browser:
        try:
            import webbrowser

            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="filigree.server")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--web", default=None)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args(argv)
    serve(args.port, args.web, args.open)
    return 0


if __name__ == "__main__":
    sys.exit(main())
