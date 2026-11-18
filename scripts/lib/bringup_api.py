#!/usr/bin/env python3
"""Moonraker HTTP client shared by scripts/bringup.sh and scripts/tmc_tune.py.

Stdlib only (urllib): no requests, no websocket.  Every method returns the
``result`` payload of the Moonraker endpoint and raises :class:`MoonrakerError`
for an HTTP/JSON error, so callers can print one readable line.

Usage as a module::

    from bringup_api import Moonraker
    api = Moonraker("http://127.0.0.1:7125")
    api.wait_ready(60)
    api.gcode("G28")

Usage as a command (handy on the printer)::

    bringup_api.py info
    bringup_api.py status                # key=value lines, safe for 'eval'
    bringup_api.py query print_stats extruder
    bringup_api.py gcode "M115"
    bringup_api.py store --count 20
    bringup_api.py wait-idle --timeout 600
    bringup_api.py restart
    bringup_api.py log-tail 50
    bringup_api.py preflight             # S0 temperature/state gate
    bringup_api.py selftest              # offline: local mock server

Exit status: 0 success, 1 a gate failed (preflight/state/timeout), 2 usage or
connection error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:7125"
DEFAULT_TIMEOUT = 10.0
#: Klipper states that may still turn into ``ready`` after a restart.
TRANSIENT_STATES = ("startup", "shutdown", "error")


class MoonrakerError(Exception):
    """Transport, HTTP or JSON error reported to the user."""


def _format_error(payload: dict, status: int) -> str:
    """Human message from a Moonraker error body.

    >>> _format_error({"error": {"message": "Klippy Host not connected"}}, 503)
    'HTTP 503: Klippy Host not connected'
    """
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or "unknown error"
        return "HTTP %d: %s" % (status, message)
    return "HTTP %d: unexpected response" % status


def parse_gcode_store(entries: list[dict], since: float | None) -> tuple[list[dict], float]:
    """Entries newer than ``since`` and the new cursor.

    Moonraker caps the store (``gcode_store_size``, 1000 on the fleet), so the
    cursor is the newest ``time`` seen: a caller that keeps it only reads new
    messages instead of re-parsing the whole buffer.

    >>> entries = [{"message": "a", "time": 1.0}, {"message": "b", "time": 2.5}]
    >>> [item["message"] for item in parse_gcode_store(entries, 1.0)[0]]
    ['b']
    >>> parse_gcode_store(entries, None)[1]
    2.5
    >>> parse_gcode_store([], 7.0)
    ([], 7.0)
    """
    if since is None:
        fresh = list(entries)
    else:
        fresh = [item for item in entries if float(item.get("time", 0)) > since]
    cursor = since if since is not None else 0.0
    for item in entries:
        cursor = max(cursor, float(item.get("time", 0)))
    return fresh, cursor


class Moonraker:
    """Minimal Moonraker client (JSON over HTTP)."""

    def __init__(self, url: str = DEFAULT_URL, timeout: float = DEFAULT_TIMEOUT):
        url = url.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = "http://" + url
        self.url = url
        self.timeout = timeout

    # -- transport ---------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: list[tuple[str, str]] | None = None,
        body: dict | None = None,
        timeout: float | None = None,
    ) -> object:
        url = self.url + path
        if params:
            url += "?" + urllib.parse.urlencode(params, doseq=True)
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(
                request, timeout=timeout or self.timeout
            ) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
                status = response.status
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {}
            raise MoonrakerError(_format_error(payload, exc.code))
        except (urllib.error.URLError, OSError) as exc:
            raise MoonrakerError("cannot reach %s: %s" % (self.url, exc))
        except ValueError as exc:
            raise MoonrakerError("invalid JSON from %s: %s" % (url, exc))
        if not isinstance(payload, dict):
            raise MoonrakerError("unexpected JSON from %s" % url)
        if payload.get("error"):
            raise MoonrakerError(_format_error(payload, status))
        return payload.get("result")

    def get(self, path: str, params: list[tuple[str, str]] | None = None) -> object:
        return self._request("GET", path, params=params)

    def post(self, path: str, body: dict | None = None,
             timeout: float | None = None) -> object:
        return self._request(
            "POST", path, body=body if body is not None else {}, timeout=timeout
        )

    # -- endpoints ---------------------------------------------------------

    def printer_info(self) -> dict:
        return self.get("/printer/info") or {}

    def server_info(self) -> dict:
        return self.get("/server/info") or {}

    def config(self) -> dict:
        status = self.query(["configfile"]).get("configfile", {})
        return status.get("config", {})

    def query(self, objects) -> dict:
        """Status of ``objects`` (bare names or ``{name: [fields]}``)."""
        params: list[tuple[str, str]] = []
        if isinstance(objects, dict):
            for name, fields in objects.items():
                params.append((name, ",".join(fields) if fields else ""))
        else:
            for name in objects:
                params.append((name, ""))
        result = self.get("/printer/objects/query", params=params) or {}
        return result.get("status", {})

    def gcode(self, script: str, timeout: float | None = None) -> object:
        """Queue a gcode script.

        Klipper executes ``gcode/script`` synchronously in its webhook handler,
        so a blocking command (``PID_CALIBRATE``, ``TEMPERATURE_WAIT``, a long
        macro such as ``TEST_SPEED``) does not return until it has finished.
        Pass a matching ``timeout`` for those calls: the default 10 s is only
        right for short commands.
        """
        return self.post("/printer/gcode/script", {"script": script}, timeout=timeout)

    def gcode_store(self, count: int = 1000) -> list[dict]:
        result = self.get("/server/gcode_store", [("count", str(count))]) or {}
        entries = result.get("gcode_store", [])
        return entries if isinstance(entries, list) else []

    def restart(self) -> object:
        """Restart Klipper through Moonraker (no sudo/systemctl).

        Newer Moonraker builds expose ``/machine/restart``; v0.10 (the bench
        runs v0.10.0-31) only has ``/machine/services/restart`` and answers 404
        to the newer path.
        """
        try:
            return self.post("/machine/restart", {"service": "klipper"})
        except MoonrakerError as exc:
            if "HTTP 404" not in str(exc):
                raise
            return self.post("/machine/services/restart", {"service": "klipper"})

    # -- state helpers -----------------------------------------------------

    def klipper_state(self) -> str:
        return str(self.printer_info().get("state", "unknown"))

    def print_state(self) -> str:
        status = self.query(["print_stats"]).get("print_stats", {})
        return str(status.get("state", "unknown"))

    def temperatures(self) -> dict:
        status = self.query(["extruder", "heater_bed"])
        extruder = status.get("extruder", {})
        bed = status.get("heater_bed", {})
        return {
            "extruder": float(extruder.get("temperature", 0.0)),
            "extruder_target": float(extruder.get("target", 0.0)),
            "heater_bed": float(bed.get("temperature", 0.0)),
            "heater_bed_target": float(bed.get("target", 0.0)),
        }

    def wait_ready(self, timeout: float = 60.0, poll: float = 1.0) -> None:
        deadline = time.time() + timeout
        while True:
            state = self.klipper_state()
            if state == "ready":
                return
            if state in ("shutdown", "error"):
                info = self.printer_info()
                raise MoonrakerError(
                    "Klipper state=%s: %s"
                    % (state, info.get("state_message", "no message"))
                )
            if time.time() >= deadline:
                raise MoonrakerError(
                    "Klipper did not become ready in %.0f s (state=%s)" % (timeout, state)
                )
            time.sleep(poll)

    def wait_print_state(
        self, states, timeout: float = 60.0, poll: float = 1.0
    ) -> str:
        wanted = {states} if isinstance(states, str) else set(states)
        deadline = time.time() + timeout
        while True:
            state = self.print_state()
            if state in wanted:
                return state
            if self.klipper_state() in ("shutdown", "error"):
                self.wait_ready(0)  # raises with the Klipper message
            if time.time() >= deadline:
                raise MoonrakerError(
                    "print_stats.state=%s did not reach %s in %.0f s"
                    % (state, "/".join(sorted(wanted)), timeout)
                )
            time.sleep(poll)

    def store_since(self, cursor: float | None, count: int = 1000):
        entries, new_cursor = parse_gcode_store(self.gcode_store(count), cursor)
        return entries, new_cursor

    def cursor(self, count: int = 1) -> float:
        """Newest ``time`` in the gcode store (0.0 when it is empty)."""
        return parse_gcode_store(self.gcode_store(count), None)[1]

    def wait_marker(
        self, marker: str, since: float, timeout: float, poll: float = 0.5
    ) -> list[dict]:
        """Wait for a ``RESPOND MSG=`` sentinel queued after a blocking macro.

        The gcode queue is sequential, so the sentinel is only printed once the
        command before it (``PID_CALIBRATE``, ``TEMPERATURE_WAIT``, a test
        macro) has finished.  This is the barrier that replaces fixed sleeps.
        """
        deadline = time.time() + timeout
        cursor = since
        collected: list[dict] = []
        while time.time() < deadline:
            entries, cursor = self.store_since(cursor)
            for item in entries:
                message = str(item.get("message", ""))
                if message.startswith("!!"):
                    # A gcode error aborts the rest of the queued script, so the
                    # marker will never arrive: fail now instead of timing out.
                    raise MoonrakerError(
                        "gcode error while waiting for %s: %s"
                        % (marker, message[2:].strip())
                    )
            collected.extend(entries)
            if any(marker in str(item.get("message", "")) for item in collected):
                return collected
            if self.klipper_state() in ("shutdown", "error"):
                raise MoonrakerError(
                    "Klipper stopped while waiting for marker %s" % marker
                )
            time.sleep(poll)
        raise MoonrakerError(
            "marker %s did not appear in %.0f s (klipper state=%s)"
            % (marker, timeout, self.klipper_state())
        )

    def verify_hold(
        self, sensor: str, target: float, seconds: float,
        tolerance: float = 1.5, poll: float = 2.0,
    ) -> dict:
        """Sample one heater for ``seconds`` and report stability."""
        key = "heater_bed" if sensor in ("heater_bed", "bed") else "extruder"
        samples: list[float] = []
        deadline = time.time() + seconds
        while time.time() < deadline:
            samples.append(self.temperatures()[key])
            time.sleep(poll)
        if not samples:
            raise MoonrakerError("no temperature samples")
        highest = max(samples)
        lowest = min(samples)
        return {
            "samples": len(samples),
            "min": lowest,
            "max": highest,
            "mean": sum(samples) / len(samples),
            "overshoot": max(0.0, highest - target),
            "within_tolerance": all(abs(value - target) <= tolerance for value in samples),
            "overshoot_warn": highest - target > 5.0,
        }

    def log_tail(self, lines: int = 50) -> list[str]:
        """Last lines of klippy.log (only when the host path is readable)."""
        path = self.printer_info().get("log_file")
        if not path or not os.path.isfile(path):
            return []
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                return fh.read().splitlines()[-lines:]
        except OSError:
            return []


# --- Command line ---------------------------------------------------------


def _shell_status(api: Moonraker) -> int:
    temps = api.temperatures()
    values = {
        "klipper_state": api.klipper_state(),
        "print_state": api.print_state(),
        "extruder": "%.2f" % temps["extruder"],
        "extruder_target": "%.2f" % temps["extruder_target"],
        "heater_bed": "%.2f" % temps["heater_bed"],
        "heater_bed_target": "%.2f" % temps["heater_bed_target"],
    }
    for key, value in values.items():
        print("%s=%s" % (key, value))
    return 0


def _preflight(api: Moonraker, max_temp: float) -> int:
    temps = api.temperatures()
    state = api.klipper_state()
    print_state = api.print_state()
    free_states = ("idle", "standby", "complete", "cancelled")
    heaters_ok = (
        temps["extruder"] < max_temp and temps["heater_bed"] < max_temp
    )
    print("klipper_state=%s" % state)
    print("print_state=%s" % print_state)
    print("extruder=%.2f" % temps["extruder"])
    print("heater_bed=%.2f" % temps["heater_bed"])
    print("heaters_ok=%d" % int(heaters_ok))
    ok = state == "ready" and print_state in free_states and heaters_ok
    print("preflight_ok=%d" % int(ok))
    if state != "ready":
        print("ERROR: Klipper state=%s" % state, file=sys.stderr)
    if print_state not in free_states:
        print("ERROR: print_stats.state=%s (printer busy)" % print_state,
              file=sys.stderr)
    if not heaters_ok:
        print("ERROR: heaters above %.0f C" % max_temp, file=sys.stderr)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Клиент Moonraker для bringup.sh и tmc_tune.py (только stdlib).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  bringup_api.py info\n"
            "  bringup_api.py status\n"
            "  bringup_api.py query print_stats\n"
            "  bringup_api.py gcode 'G28'\n"
            "  bringup_api.py wait-idle --timeout 600\n"
            "  bringup_api.py selftest\n"
        ),
    )
    parser.add_argument("--url", default=os.environ.get("MOONRAKER_URL", DEFAULT_URL),
                        help="адрес Moonraker (по умолчанию %s)" % DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="таймаут одного HTTP-запроса, с")
    parser.add_argument("command", nargs="?",
                        help="info|status|query|gcode|store|restart|wait-ready|"
                             "wait-idle|log-tail|preflight|selftest")
    parser.add_argument("args", nargs="*", help="аргументы команды")
    parser.add_argument("--count", type=int, default=1000, help="store: строк")
    parser.add_argument("--wait", type=float, default=600.0,
                        help="wait-*: общий таймаут, с")
    parser.add_argument("--max-temp", type=float, default=45.0,
                        help="preflight: максимальная температура нагревателей")
    parser.add_argument("--marker", help="wait-marker: строка-маркер RESPOND")
    parser.add_argument("--since", type=float,
                        help="wait-marker: читать gcode_store новее этого time")
    parser.add_argument("--sensor", help="verify-hold: extruder или heater_bed")
    parser.add_argument("--target", type=float, help="verify-hold: целевая температура")
    parser.add_argument("--hold", type=float, default=30.0,
                        help="verify-hold: длительность выборки, с")
    parser.add_argument("--tolerance", type=float, default=1.5,
                        help="verify-hold: допуск, °C")
    parser.add_argument("--poll", type=float, default=2.0,
                        help="verify-hold: период опроса, с")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "selftest":
        return selftest()
    if not args.command:
        print("ERROR: команда не указана (см. --help)", file=sys.stderr)
        return 2
    api = Moonraker(args.url, args.timeout)
    try:
        if args.command == "info":
            print(json.dumps(api.printer_info(), ensure_ascii=False, indent=2))
        elif args.command == "status":
            return _shell_status(api)
        elif args.command == "preflight":
            return _preflight(api, args.max_temp)
        elif args.command == "query":
            if not args.args:
                print("ERROR: query needs at least one object", file=sys.stderr)
                return 2
            print(json.dumps(api.query(args.args), ensure_ascii=False, indent=2))
        elif args.command == "gcode":
            if not args.args:
                print("ERROR: gcode needs a script", file=sys.stderr)
                return 2
            api.gcode(" ".join(args.args))
        elif args.command == "restart":
            api.restart()
            print("restart: запрос на перезапуск Klipper отправлен")
        elif args.command == "store":
            print(json.dumps(api.gcode_store(args.count), ensure_ascii=False, indent=2))
        elif args.command == "cursor":
            print("%.6f" % api.cursor())
        elif args.command == "wait-marker":
            if not args.marker:
                print("ERROR: wait-marker needs --marker", file=sys.stderr)
                return 2
            if args.since is None:
                print("ERROR: wait-marker needs --since (use 'cursor')", file=sys.stderr)
                return 2
            entries = api.wait_marker(args.marker, args.since, args.wait)
            print(json.dumps(entries, ensure_ascii=False, indent=2))
        elif args.command == "verify-hold":
            if args.sensor is None or args.target is None:
                print("ERROR: verify-hold needs --sensor and --target", file=sys.stderr)
                return 2
            stats = api.verify_hold(
                args.sensor, args.target, args.hold, args.tolerance, args.poll
            )
            for key_name, value in stats.items():
                if isinstance(value, bool):
                    print("%s=%d" % (key_name, int(value)))
                elif isinstance(value, float):
                    print("%s=%.3f" % (key_name, value))
                else:
                    print("%s=%s" % (key_name, value))
        elif args.command == "wait-ready":
            api.wait_ready(args.wait)
            print("klipper_state=ready")
        elif args.command == "wait-idle":
            state = api.wait_print_state(
                ("idle", "standby", "complete", "cancelled"), args.wait
            )
            print("print_state=%s" % state)
        elif args.command == "log-tail":
            count = int(args.args[0]) if args.args else 50
            for line in api.log_tail(count):
                print(line)
        else:
            print("ERROR: неизвестная команда %r" % args.command, file=sys.stderr)
            return 2
    except MoonrakerError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1
    return 0


# --- Offline selftest -----------------------------------------------------


def selftest() -> int:
    """Exercise the client against a local mock Moonraker (no printer)."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    state = {"restarts": 0, "scripts": [], "polls": 0, "legacy": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence the test server
            pass

        def _send(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/printer/info":
                state["polls"] += 1
                # First two polls report startup, then ready.
                current = "startup" if state["polls"] <= 2 else "ready"
                self._send({"result": {"state": current, "log_file": "/nonexistent"}})
            elif path == "/server/info":
                self._send({"result": {"moonraker_version": "test"}})
            elif path == "/printer/objects/query":
                self._send({"result": {"status": {
                    "print_stats": {"state": "printing"},
                    "extruder": {"temperature": 21.5, "target": 0},
                    "heater_bed": {"temperature": 22.0, "target": 0},
                }}})
            elif path == "/server/gcode_store":
                self._send({"result": {"gcode_store": [
                    {"message": "// old", "time": 1.0},
                    {"message": "// pid_Kp=1", "time": 2.0},
                ]}})
            else:
                self._send({"error": {"message": "not found"}}, 404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            if self.path.startswith("/printer/gcode/script"):
                state["scripts"].append(body.get("script"))
                self._send({"result": "ok"})
            elif self.path.startswith("/machine/restart"):
                if state["legacy"]:
                    self._send({"error": {"message": "not found"}}, 404)
                else:
                    state["restarts"] += 1
                    self._send({"result": "ok"})
            elif self.path.startswith("/machine/services/restart"):
                state["restarts"] += 1
                self._send({"result": "ok"})
            else:
                self._send({"error": {"message": "not found"}}, 404)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    failures = 0

    def check(label: str, ok: bool) -> None:
        nonlocal failures
        print("  %-40s %s" % (label, "ok" if ok else "MISMATCH"))
        failures += 0 if ok else 1

    try:
        api = Moonraker("http://127.0.0.1:%d" % server.server_port, timeout=5)
        check("server_info", api.server_info()["moonraker_version"] == "test")
        api.wait_ready(10, poll=0.05)
        check("wait_ready polls startup then ready", state["polls"] >= 3)
        check("print_state", api.print_state() == "printing")
        temps = api.temperatures()
        check("temperatures", abs(temps["extruder"] - 21.5) < 1e-9)
        api.gcode("G28")
        check("gcode script posted", state["scripts"] == ["G28"])
        entries, cursor = api.store_since(None)
        check("gcode_store count", len(entries) == 2 and cursor == 2.0)
        fresh, _ = api.store_since(1.5)
        check("store cursor filters old entries", len(fresh) == 1)
        api.restart()
        check("restart falls back to services/restart", state["restarts"] == 1)
        state["legacy"] = False
        api.restart()
        check("restart uses /machine/restart when present", state["restarts"] == 2)
        try:
            api.get("/missing")
        except MoonrakerError as exc:
            check("404 mapped to MoonrakerError", "not found" in str(exc))
        else:
            check("404 mapped to MoonrakerError", False)
    finally:
        server.shutdown()
        server.server_close()
    print("bringup_api selftest: %s" % ("FAILED" if failures else "ok"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())