#!/usr/bin/env python3
"""Resumable state of one ``bringup.sh`` run (JSON, atomic writes).

The file lives outside the repository (``~/printer_data/.bringup/<id>.json``)
because it describes one machine's commissioning, not the shared config.  It
records the last finished stage, the repository commit the run started from and
an append-only log of stage attempts, so ``bringup.sh --from`` can resume.

Structure::

    {
      "profile": "voron-t",
      "stage": "tmc",                 # last finished stage
      "current": null,                # stage in progress, if any
      "repo_head": "abc123",
      "started": "2026-11-15T18:00:00+00:00",
      "updated": "...",
      "runs": [{"stage": "deploy", "status": "ok", "started": "...",
                "finished": "...", "note": "..."}]
    }

Usage:
  bringup_state.py --file ~/printer_data/.bringup/voron-t.json show
  bringup_state.py --file ... begin --stage tmc --repo-head abc123
  bringup_state.py --file ... finish --stage tmc --status ok --note "4 modules"
  bringup_state.py --file ... reset
  bringup_state.py --file ... selftest

``show`` prints ``key=value`` lines that bash can ``eval``.
Exit status: 0 success, 1 invalid state, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

STAGES = ("deploy", "tmc", "motion", "pid-e", "pid-b", "done")
STATUSES = ("ok", "fail", "skip")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_state(profile: str, repo_head: str = "") -> dict:
    """Fresh state for a profile.

    >>> state = new_state("voron-t", "abc")
    >>> (state["profile"], state["stage"], state["runs"])
    ('voron-t', '', [])
    """
    stamp = now()
    return {
        "profile": profile,
        "stage": "",
        "current": None,
        "repo_head": repo_head,
        "started": stamp,
        "updated": stamp,
        "runs": [],
    }


def load(path: str, profile: str) -> dict:
    if not os.path.isfile(path):
        return new_state(profile)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read %s: %s" % (path, exc))
    if not isinstance(state, dict):
        raise ValueError("%s does not hold a JSON object" % path)
    state.setdefault("profile", profile)
    state.setdefault("stage", "")
    state.setdefault("current", None)
    state.setdefault("repo_head", "")
    state.setdefault("runs", [])
    if state["profile"] != profile:
        raise ValueError(
            "%s belongs to profile %r, not %r" % (path, state["profile"], profile)
        )
    return state


def save(path: str, state: dict) -> None:
    state["updated"] = now()
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".bringup-", dir=directory)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def last_status(state: dict, stage: str) -> str | None:
    for run in reversed(state.get("runs", [])):
        if run.get("stage") == stage:
            return str(run.get("status"))
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Состояние прогона bringup.sh (JSON, атомарная запись).",
    )
    parser.add_argument("--file", help="путь к файлу состояния (кроме selftest)")
    parser.add_argument("--profile", default="", help="id профиля (проверка)")
    parser.add_argument("command", choices=("show", "begin", "finish", "reset", "selftest"))
    parser.add_argument("--stage", choices=STAGES)
    parser.add_argument("--status", choices=STATUSES)
    parser.add_argument("--note", default="")
    parser.add_argument("--repo-head", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "selftest":
        return selftest()
    if not args.file:
        print("ERROR: --file is required", file=sys.stderr)
        return 2
    profile = args.profile or os.path.basename(args.file).rsplit(".", 1)[0]
    try:
        state = load(args.file, profile)
    except ValueError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1

    if args.command == "show":
        print("profile=%s" % state["profile"])
        print("stage=%s" % state["stage"])
        print("current=%s" % (state["current"] or ""))
        print("repo_head=%s" % state["repo_head"])
        print("runs=%d" % len(state["runs"]))
        for stage in STAGES:
            print("status_%s=%s" % (stage.replace("-", "_"),
                                    last_status(state, stage) or ""))
        return 0

    if args.command == "begin":
        if not args.stage:
            print("ERROR: begin needs --stage", file=sys.stderr)
            return 2
        state["current"] = {"stage": args.stage, "started": now()}
        if args.repo_head:
            state["repo_head"] = args.repo_head
        save(args.file, state)
        return 0

    if args.command == "finish":
        if not args.stage or not args.status:
            print("ERROR: finish needs --stage and --status", file=sys.stderr)
            return 2
        started = now()
        current = state.get("current") or {}
        if current.get("stage") == args.stage:
            started = str(current.get("started") or started)
        state["runs"].append({
            "stage": args.stage,
            "status": args.status,
            "started": started,
            "finished": now(),
            "note": args.note,
        })
        state["current"] = None
        if args.status == "ok":
            state["stage"] = args.stage
        save(args.file, state)
        return 0

    if args.command == "reset":
        save(args.file, new_state(profile, args.repo_head))
        return 0

    return 2


def selftest() -> int:
    import doctest

    failures = doctest.testmod(sys.modules[__name__], verbose=False)
    print("doctest: %d failed, %d run" % (failures.failed, failures.attempted))
    bad = failures.failed
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "state.json")
        state = load(path, "demo")
        state["current"] = {"stage": "deploy", "started": now()}
        save(path, state)
        state = load(path, "demo")
        state["runs"].append({"stage": "deploy", "status": "ok"})
        state["current"] = None
        state["stage"] = "deploy"
        save(path, state)
        again = load(path, "demo")
        if again["stage"] != "deploy" or last_status(again, "deploy") != "ok":
            bad += 1
            print("MISMATCH: state round-trip")
        try:
            load(path, "other")
        except ValueError:
            pass
        else:
            bad += 1
            print("MISMATCH: profile mismatch not detected")
    print("bringup_state selftest: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())