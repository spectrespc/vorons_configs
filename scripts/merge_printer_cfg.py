#!/usr/bin/env python3
"""Merge the managed printer.cfg head with the live SAVE_CONFIG block.

deploy_configs.sh replaces everything above the ``#*# <... SAVE_CONFIG ...>``
marker with the repository copy of ``printers/<profile>/printer.cfg`` and keeps
the autosave block (Klipper's calibrated values) from the live file.

Klipper gives the regular config priority over the autosave: in
``configfile.load_main_config()`` it comments out autosave options that the head
already defines.  A freshly seeded head would therefore shadow every calibrated
value, so this script also comments out head options that the preserved
autosave defines - exactly the state Klipper leaves behind after SAVE_CONFIG.

Usage:
  merge_printer_cfg.py --head SEED --live LIVE --output OUT

Prints ``updated`` or ``unchanged``; the caller compares the output with LIVE
to decide whether a backup and rewrite are needed.
"""

from __future__ import annotations

import argparse
import io
import re
import sys

MARKER_RE = re.compile(r"^#\*# <.*SAVE_CONFIG")
SECTION_RE = re.compile(r"^#\*#\s*\[(.+?)\]\s*$")
OPTION_RE = re.compile(r"^#\*#\s*([A-Za-z0-9_]+)\s*=")
HEAD_SECTION_RE = re.compile(r"^\[(.+?)\]")
HEAD_OPTION_RE = re.compile(r"^([A-Za-z0-9_]+)\s*[:=]")


def split_autosave(text: str) -> tuple[str, str]:
    """Split a printer.cfg into (head, autosave tail).

    The tail starts at the SAVE_CONFIG marker line and is returned verbatim,
    marker included.

    >>> split_autosave("head\\n#*# <-- SAVE_CONFIG -->\\n#*# [a]\\n")
    ('head\\n', '#*# <-- SAVE_CONFIG -->\\n#*# [a]\\n')
    >>> split_autosave("only head\\n")
    ('only head\\n', '')
    """
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if MARKER_RE.match(line):
            return "".join(lines[:index]), "".join(lines[index:])
    return text, ""


def autosave_options(tail: str) -> dict[str, set[str]]:
    """Return {section: {option}} for the options inside the autosave block.

    >>> sorted(autosave_options(
    ...     "#*# <-- SAVE_CONFIG -->\\n"
    ...     "#*# [stepper_z]\\n#*# position_endstop = -0.030\\n"
    ...     "#*# [probe_eddy_current fly_eddy_probe]\\n"
    ...     "#*# calibrate =\\n#*# \\t0.05:4682387\\n"
    ... ).items())
    [('probe_eddy_current fly_eddy_probe', {'calibrate'}), ('stepper_z', {'position_endstop'})]
    """
    options: dict[str, set[str]] = {}
    section: str | None = None
    for line in tail.splitlines():
        section_match = SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1).strip()
            options.setdefault(section, set())
            continue
        option_match = OPTION_RE.match(line)
        if option_match and section is not None:
            options[section].add(option_match.group(1).lower())
    return options


def comment_shadowed(head: str, shadowed: dict[str, set[str]]) -> str:
    """Comment out head options that the autosave block already defines.

    Klipper ignores an autosave option when the regular config defines it, so
    leaving the seeded value active would silently discard the calibration.

    >>> comment_shadowed(
    ...     "[stepper_z]\\nposition_endstop: -0.520\\nposition_max: 340\\n",
    ...     {"stepper_z": {"position_endstop"}},
    ... )
    '[stepper_z]\\n#position_endstop: -0.520\\nposition_max: 340\\n'
    >>> comment_shadowed("[a]\\nx: 1\\n", {})
    '[a]\\nx: 1\\n'
    """
    lines = head.splitlines(keepends=True)
    section: str | None = None
    commenting = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if line[:1].isspace():
            if commenting:
                lines[index] = "#" + line
            continue
        commenting = False
        section_match = HEAD_SECTION_RE.match(line)
        if section_match:
            section = section_match.group(1).strip()
            continue
        option_match = HEAD_OPTION_RE.match(line)
        if option_match and section is not None:
            name = option_match.group(1).lower()
            if name in shadowed.get(section, ()):  # type: ignore[arg-type]
                commenting = True
                lines[index] = "#" + line
    return "".join(lines)


def merge(head_text: str, live_text: str) -> str:
    """Return the new printer.cfg: managed head + preserved autosave.

    >>> seed = "[include profile.cfg]\\n\\n[stepper_z]\\nposition_endstop: -0.520\\n"
    >>> live = (seed + "\\n#*# <-- SAVE_CONFIG -->\\n#*# [stepper_z]\\n"
    ...         "#*# position_endstop = -0.030\\n")
    >>> out = merge(seed, live)
    >>> "#position_endstop: -0.520" in out and "#*# position_endstop = -0.030" in out
    True
    >>> merge(seed, live) == merge(seed, out)
    True
    """
    _, tail = split_autosave(live_text)
    head = comment_shadowed(head_text, autosave_options(tail))
    if not tail:
        return head
    if not head.endswith("\n"):
        head += "\n"
    return head + "\n" + tail


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Merge a printer.cfg head with the live SAVE_CONFIG block."
    )
    parser.add_argument("--head", required=True, help="repository seed to install")
    parser.add_argument("--live", help="current live printer.cfg (optional)")
    parser.add_argument("--output", required=True, help="where to write the result")
    args = parser.parse_args(argv)

    with io.open(args.head, "r", encoding="utf-8", newline="") as fh:
        head_text = fh.read()
    live_text = ""
    if args.live:
        try:
            with io.open(args.live, "r", encoding="utf-8", newline="") as fh:
                live_text = fh.read()
        except FileNotFoundError:
            live_text = ""

    result = merge(head_text, live_text)
    with io.open(args.output, "w", encoding="utf-8", newline="") as fh:
        fh.write(result)
    print("unchanged" if result == live_text else "updated")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))