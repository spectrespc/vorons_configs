#!/usr/bin/env python3
"""PID_CALIBRATE result parsing and pid.cfg patching for bringup.sh.

``SAVE_CONFIG`` is deliberately not used: the calibrated values are written
into ``printers/<id>/local/pid.cfg`` in the repository, deployed and applied by
a Klipper restart, so the repository stays the source of truth.

Usage:
  bringup_api.py store --count 1000 | bringup_pid.py parse --since 123.4
  bringup_pid.py patch --file printers/voron-t/local/pid.cfg \\
      --section extruder --kp 32.2 --ki 2.49 --kd 103.8 --date 2026-11-15
  bringup_pid.py selftest

``parse`` reads the gcode_store JSON (a list of ``{"message": ...,"time": ...}``)
from stdin, keeps messages newer than ``--since`` and prints the last
``pid_Kp/pid_Ki/pid_Kd`` triple as shell ``key=value`` lines.  ``patch`` is
atomic and idempotent: the file is only rewritten when a value or the
calibration comment actually changes; stdout reports ``changed=0|1``.

Exit status: 0 success, 1 no PID line found, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

PID_RE = re.compile(
    r"pid_Kp\s*=\s*([-\d.]+)\s+pid_Ki\s*=\s*([-\d.]+)\s+pid_Kd\s*=\s*([-\d.]+)"
)
COMMENT_RE = re.compile(r"^#\s*calibrated\s+\S+\s+by\s+bringup\.sh\s*$")
PID_KEYS = ("pid_kp", "pid_ki", "pid_kd")


def parse_pid_messages(messages: list[str]) -> tuple[float, float, float] | None:
    """Last PID triple in a list of gcode_store messages.

    >>> parse_pid_messages(["// noise",
    ...                     "// pid_Kp=32.208 pid_Ki=2.497 pid_Kd=103.871"])
    (32.208, 2.497, 103.871)
    >>> parse_pid_messages(["// pid_Kp=1 pid_Ki=2 pid_Kd=3",
    ...                     "// pid_Kp=4 pid_Ki=5 pid_Kd=6"])
    (4.0, 5.0, 6.0)
    >>> parse_pid_messages([]) is None
    True
    """
    found = None
    for message in messages:
        for match in PID_RE.finditer(str(message)):
            found = tuple(float(value) for value in match.groups())
    return found  # type: ignore[return-value]


def filter_since(entries: list[dict], since: float | None) -> list[dict]:
    """Entries strictly newer than ``since`` (a Moonraker ``time`` value).

    >>> entries = [{"message": "a", "time": 1.0}, {"message": "b", "time": 2.0}]
    >>> [item["message"] for item in filter_since(entries, 1.5)]
    ['b']
    >>> len(filter_since(entries, None))
    2
    """
    if since is None:
        return list(entries)
    return [item for item in entries if float(item.get("time", 0)) > since]


def patch_pid_text(
    text: str, section: str, kp: float, ki: float, kd: float, date: str
) -> tuple[str, bool]:
    """Insert or update the PID block of one section.

    >>> text = "[extruder]\\npid_kp: 1.0\\npid_ki: 2.0\\npid_kd: 3.0\\n"
    >>> new, changed = patch_pid_text(text, "extruder", 4.0, 5.0, 6.0, "2026-11-15")
    >>> changed, "pid_kp: 4" in new, new.count("[extruder]")
    (True, True, 1)
    >>> again, changed_again = patch_pid_text(new, "extruder", 4.0, 5.0, 6.0, "2026-11-15")
    >>> changed_again, again == new
    (False, True)
    >>> empty, _ = patch_pid_text("", "heater_bed", 1, 2, 3, "2026-11-15")
    >>> empty.splitlines()[0]
    '[heater_bed]'
    """
    header = "[%s]" % section
    lines = text.splitlines()
    start = None
    for index, line in enumerate(lines):
        if line.strip() == header:
            start = index
            break
    values = {
        "pid_kp": "%.3f" % kp,
        "pid_ki": "%.3f" % ki,
        "pid_kd": "%.3f" % kd,
    }
    comment = "# calibrated %s by bringup.sh" % date

    if start is None:
        block = [header, comment]
        block.extend("%s: %s" % (key, values[key]) for key in PID_KEYS)
        new_text = "\n".join(lines + ([""] if lines and lines[-1].strip() else [])
                             + block) + "\n"
        return new_text, new_text != text

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].strip().startswith("["):
            end = index
            break
    body = lines[start + 1:end]
    seen: set[str] = set()
    comment_seen = False
    new_body: list[str] = []
    for line in body:
        stripped = line.strip()
        if COMMENT_RE.match(stripped):
            new_body.append(comment)
            comment_seen = True
            continue
        key = stripped.split(":", 1)[0].strip() if ":" in stripped else ""
        if key in values and not stripped.startswith("#"):
            new_body.append("%s: %s" % (key, values[key]))
            seen.add(key)
            continue
        new_body.append(line)
    missing = [key for key in PID_KEYS if key not in seen]
    if not comment_seen:
        new_body.insert(0, comment)
    if missing:
        insert_at = len(new_body)
        while insert_at > 0 and not new_body[insert_at - 1].strip():
            insert_at -= 1
        last_active = None
        for index, line in enumerate(new_body[:insert_at]):
            if ":" in line and not line.strip().startswith("#"):
                last_active = index
        insert_at = (last_active + 1) if last_active is not None else 0
        new_body[insert_at:insert_at] = [
            "%s: %s" % (key, values[key]) for key in missing
        ]
    new_lines = lines[:start + 1] + new_body + lines[end:]
    new_text = "\n".join(new_lines) + "\n"
    return new_text, new_text != text


def write_atomic(path: str, text: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".pid-", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        if os.path.exists(path):
            os.chmod(temporary, os.stat(path).st_mode & 0o777)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Разбор ответа PID_CALIBRATE и патч pid.cfg (stdlib, атомарно).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  bringup_api.py store | bringup_pid.py parse --since 123.4\n"
            "  bringup_pid.py patch --file printers/voron-t/local/pid.cfg "
            "--section extruder --kp 32.2 --ki 2.49 --kd 103.8\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    parse = sub.add_parser("parse", help="PID из JSON gcode_store на stdin")
    parse.add_argument("--since", type=float, help="читать только новее этого time")
    patch = sub.add_parser("patch", help="записать PID в pid.cfg")
    patch.add_argument("--file", required=True)
    patch.add_argument("--section", required=True)
    patch.add_argument("--kp", type=float, required=True)
    patch.add_argument("--ki", type=float, required=True)
    patch.add_argument("--kd", type=float, required=True)
    patch.add_argument("--date", help="ISO-дата для комментария (по умолчанию сегодня)")
    patch.add_argument("--dry-run", action="store_true", help="не писать файл")
    sub.add_parser("selftest", help="офлайн-проверки")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "selftest":
        return selftest()
    if args.command == "parse":
        try:
            payload = json.load(sys.stdin)
        except (OSError, ValueError) as exc:
            print("ERROR: cannot parse gcode_store JSON: %s" % exc, file=sys.stderr)
            return 2
        entries = payload if isinstance(payload, list) else payload.get("gcode_store", [])
        messages = [str(item.get("message", "")) for item in filter_since(entries, args.since)]
        pid = parse_pid_messages(messages)
        if pid is None:
            print("ERROR: no pid_Kp/pid_Ki/pid_Kd line in the gcode store", file=sys.stderr)
            return 1
        print("kp=%.3f" % pid[0])
        print("ki=%.3f" % pid[1])
        print("kd=%.3f" % pid[2])
        return 0

    from datetime import date

    stamp = args.date or date.today().isoformat()
    try:
        with open(args.file, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        print("ERROR: cannot read %s: %s" % (args.file, exc), file=sys.stderr)
        return 2
    new_text, changed = patch_pid_text(
        text, args.section, args.kp, args.ki, args.kd, stamp
    )
    if changed and not args.dry_run:
        write_atomic(args.file, new_text)
    print("changed=%d" % int(changed))
    print("file=%s" % args.file)
    return 0


def selftest() -> int:
    import doctest

    failures = doctest.testmod(sys.modules[__name__], verbose=False)
    print("doctest: %d failed, %d run" % (failures.failed, failures.attempted))
    bad = failures.failed
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "pid.cfg")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "[extruder]\n#pid_Kp=32.208 pid_Ki=2.497 pid_Kd=103.871\n"
                "pid_kp: 32.208\npid_ki: 2.497\npid_kd: 103.871\n\n"
                "[heater_bed]\npid_kp: 66.480\npid_ki: 2.462\npid_kd: 448.743\n"
            )
        first, changed = patch_pid_text(
            open(path, encoding="utf-8").read(), "extruder", 40.0, 3.0, 120.0,
            "2026-11-15",
        )
        second, changed_again = patch_pid_text(
            first, "extruder", 40.0, 3.0, 120.0, "2026-11-15"
        )
        if not changed or changed_again or first != second:
            bad += 1
            print("MISMATCH: pid patch is not idempotent")
        if "pid_kp: 66.480" not in second:
            bad += 1
            print("MISMATCH: another section was modified")
        if first.count("by bringup.sh") != 1:
            bad += 1
            print("MISMATCH: calibration comment duplicated")
    print("bringup_pid selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())