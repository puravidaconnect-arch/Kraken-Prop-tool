"""One-page local form that journals a trade without the terminal (Phase 5b).
Standard library only. It calls the same functions as `python -m src.report`,
so the JSON it writes is identical.

  python -m src.form            # http://127.0.0.1:8765 on this machine only
  python -m src.form --lan      # also reachable from your phone on the home network

Nothing here sends orders. It only writes journal/*.json.
"""
from __future__ import annotations

import argparse
import html
import socket
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from src import journal
from src.report import cancel_ticket, close_ticket, mark_open, pending_reports
from src.state import DEFAULT, Paths

PORT = 8765

CSS = """
body{font:17px/1.4 -apple-system,system-ui,sans-serif;margin:0;padding:12px;background:#f5f5f7;color:#111}
h1{font-size:20px;margin:6px 0 12px}h2{font-size:17px;margin:0 0 8px}
.card{background:#fff;border-radius:12px;padding:14px;margin:0 0 14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.plan{color:#555;font-size:14px;margin:0 0 10px}
label{display:block;font-size:14px;color:#444;margin:8px 0 2px}
input,textarea,select{width:100%;box-sizing:border-box;font-size:17px;padding:10px;border:1px solid #ccc;border-radius:8px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.row>div{min-width:0}
@media (max-width:480px){.row{grid-template-columns:1fr}}
button{width:100%;font-size:17px;padding:12px;border:0;border-radius:10px;margin-top:12px;color:#fff;background:#1a73e8}
button.warn{background:#c62828}button.grey{background:#666}
.msg{padding:10px 14px;border-radius:10px;margin-bottom:14px;background:#e8f5e9;color:#1b5e20}
.msg.err{background:#fdecea;color:#b71c1c}
details summary{cursor:pointer;font-weight:600;margin-top:8px}
.small{font-size:13px;color:#666}
"""


def _e(v) -> str:
    return html.escape("" if v is None else str(v))


def worst_entry(t: dict) -> float:
    return max(t["entry_zone"]) if t["direction"] == "long" else min(t["entry_zone"])


def close_form(t: dict) -> str:
    return f"""
<form method="post" action="/close">
<input type="hidden" name="id" value="{_e(t['id'])}">
<div class="row">
<div><label>fill price</label><input name="fill_price" inputmode="decimal" required value="{_e(t.get('fill_price') or worst_entry(t))}"></div>
<div><label>exit price</label><input name="exit_price" inputmode="decimal" required></div>
</div>
<div class="row">
<div><label>quantity ({_e(t['pair'])})</label><input name="position_qty" inputmode="decimal" required value="{_e(t['position_qty'])}"></div>
<div><label>result USD (net, signed)</label><input name="result_usd" inputmode="decimal" required placeholder="-24.60"></div>
</div>
<div class="row">
<div><label>opened at</label><input type="datetime-local" name="opened_at" required value="{_e(t.get('opened_at') or '')}"></div>
<div><label>closed at</label><input type="datetime-local" name="closed_at" required></div>
</div>
<label>followed plan?</label>
<select name="followed_plan"><option value="yes">yes</option><option value="no">no</option></select>
<label>deviation note (required if no)</label><input name="deviation_note">
<label>mid-trade events</label><input name="mid_trade_events" value="none">
<label>emotion note</label><input name="emotion_note" placeholder="calm / anxious / bored…">
<label><input type="checkbox" name="force" value="1" style="width:auto"> numbers are right even if the sanity check complains</label>
<button type="submit">Close trade → journal</button>
</form>"""


def open_form(t: dict) -> str:
    return f"""
<form method="post" action="/open">
<input type="hidden" name="id" value="{_e(t['id'])}">
<div class="row">
<div><label>fill price</label><input name="fill_price" inputmode="decimal" required value="{_e(worst_entry(t))}"></div>
<div><label>opened at</label><input type="datetime-local" name="opened_at" required></div>
</div>
<button type="submit" class="grey">Mark filled (open)</button>
</form>
<form method="post" action="/cancel">
<input type="hidden" name="id" value="{_e(t['id'])}">
<label>cancel note</label><input name="note" placeholder="never filled">
<button type="submit" class="warn">Cancel plan (never filled)</button>
</form>"""


def ticket_card(t: dict) -> str:
    plan = (f"{t['direction']} · zone {t['entry_zone'][0]}–{t['entry_zone'][1]} · stop {t['stop']} · target {t['target']} · "
            f"qty {t['position_qty']} · risk ${t['risk_usd']}" + (f" · filled @ {t['fill_price']} {t['opened_at']}" if t["status"] == "open" else ""))
    body = close_form(t) if t["status"] == "open" else (
        f"<details open><summary>Close it (filled and already closed)</summary>{close_form(t)}</details>"
        f"<details><summary>Still open, or never filled</summary>{open_form(t)}</details>")
    return f'<div class="card"><h2>{_e(t["id"])} <span class="small">[{_e(t["status"])}]</span></h2><p class="plan">{_e(plan)}</p>{body}</div>'


def render_page(paths: Paths, message: str | None = None, error: bool = False) -> str:
    pending = pending_reports(paths.journal)
    closed = [t for t in journal.list_tickets("closed", paths.journal)][-5:]
    parts = [f"<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
             f"<title>Trade journal</title><style>{CSS}</style><h1>Trade journal</h1>"]
    if message:
        parts.append(f'<div class="msg{" err" if error else ""}">{_e(message)}</div>')
    parts += [ticket_card(t) for t in pending] or ['<div class="card">No planned or open tickets. Run /plan first.</div>']
    if closed:
        parts.append('<div class="card"><h2>Recently closed</h2>' + "".join(
            f'<p class="small">{_e(t["id"])} · {_e(t["outcome"])} · {t["result_usd"]:+.2f} · reviewed: {"yes" if t.get("review_tag") else "no (at /wrap)"}</p>'
            for t in reversed(closed)) + "</div>")
    parts.append('<p class="small">Writes journal/*.json only. The reviewer runs at /wrap. Nothing here sends orders.</p>')
    return "".join(parts)


def _f(form: dict, key: str) -> float:
    v = (form.get(key) or "").strip().replace(",", "")
    if v == "":
        raise ValueError(f"{key} is required")
    return float(v)


def handle_action(action: str, form: dict, paths: Paths) -> tuple[bool, str]:
    """Apply a POSTed form. Returns (ok, message). Same functions as /report."""
    try:
        tid = form["id"]
        if action == "open":
            t = mark_open(tid, _f(form, "fill_price"), form["opened_at"], paths.journal)
            return True, f"{t['id']} marked open at {t['fill_price']}"
        if action == "close":
            t = close_ticket(
                tid, fill_price=_f(form, "fill_price"), exit_price=_f(form, "exit_price"),
                position_qty=_f(form, "position_qty"), result_usd=_f(form, "result_usd"),
                opened_at=form["opened_at"], closed_at=form["closed_at"],
                followed_plan=form.get("followed_plan", "yes") == "yes",
                deviation_note=(form.get("deviation_note") or "").strip() or None,
                mid_trade_events=(form.get("mid_trade_events") or "").strip() or None,
                emotion_note=(form.get("emotion_note") or "").strip() or None,
                force=form.get("force") == "1", journal_dir=paths.journal)
            return True, f"{t['id']} closed: {t['outcome']} {t['result_usd']:+.2f}. Reviewer runs at /wrap."
        if action == "cancel":
            t = cancel_ticket(tid, (form.get("note") or "").strip() or None, paths.journal)
            return True, f"{t['id']} cancelled"
        return False, f"unknown action {action}"
    except (KeyError, ValueError, FileNotFoundError) as exc:
        return False, f"REPORT REFUSED: {exc}"


def make_handler(paths: Paths):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, body: str, status=HTTPStatus.OK, headers=()):
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            for k, v in headers:
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path, _, query = self.path.partition("?")
            if path != "/":
                return self._send("not found", HTTPStatus.NOT_FOUND)
            q = {k: v[0] for k, v in parse_qs(query).items()}
            self._send(render_page(paths, q.get("msg"), q.get("err") == "1"))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode("utf-8")).items()}
            ok, msg = handle_action(self.path.strip("/"), form, paths)
            self._send("", HTTPStatus.SEE_OTHER, [("Location", "/?" + urlencode({"msg": msg, "err": "0" if ok else "1"}))])

        def log_message(self, fmt, *args):  # quiet
            pass

    return Handler


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def serve(host: str, port: int, paths: Paths = DEFAULT) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(paths))
    shown = lan_ip() if host == "0.0.0.0" else host
    print(f"trade journal form: http://{shown}:{port}/   (Ctrl-C to stop)")
    if host == "0.0.0.0":
        print("  reachable by any device on your network; no login. Stop it when you are done.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Local one-page trade journal form.")
    ap.add_argument("--lan", action="store_true", help="bind 0.0.0.0 so your phone on the home network can reach it")
    ap.add_argument("--port", type=int, default=PORT)
    args = ap.parse_args(argv)
    serve("0.0.0.0" if args.lan else "127.0.0.1", args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
