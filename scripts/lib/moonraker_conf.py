#!/usr/bin/env python3
"""Keep the canonical [update_manager vorons_configs] entry in moonraker.conf.

Moonraker reads the update_manager sections only at startup, so the live file
must already contain the canonical entry before the first automatic update.
This helper runs after a deploy (``scripts/deploy_configs.sh``) and after a pull
(``scripts/moonraker_update.sh``); it is idempotent.

The file is edited as text on purpose: Moonraker allows comments and the fleet
files carry hand-written ones, which a configparser round trip would drop.

An entry counts as ours when its ``path`` expands to the target path, when its
section name is the target name, or when its ``origin`` points at the same
repository (the legacy ``~/vorons_configs_local`` checkout). The first match is
replaced in place, the other matches are removed, and every unrelated section
and comment is kept verbatim.

Usage::

    moonraker_conf.py ensure --config ~/printer_data/config/moonraker.conf
    moonraker_conf.py ensure --config FILE --dry-run
    moonraker_conf.py selftest

Exit status: 0 success (including the "unchanged" result), 1 the file could not
be read or written, 2 usage error.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import sys
import tempfile

DEFAULT_NAME = "vorons_configs"
DEFAULT_PATH = "~/vorons_configs"
DEFAULT_ORIGIN = "https://github.com/spectrespc/vorons_configs"
DEFAULT_BRANCH = "main"
#: Moonraker never executes "install_script" (it only parses it for PKGLIST),
#: and restarting klipper is done by scripts/moonraker_update.sh after the
#: deploy, so the canonical entry carries neither option.
DEFAULT_MANAGED_SERVICES = ""
DEFAULT_INSTALL_SCRIPT = ""

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[#;].*)?$")
OPTION_RE = re.compile(r"^([A-Za-z0-9_]+)\s*[:=]\s*(.*)$")
UPDATE_MANAGER_PREFIX = "update_manager"


class Section:
    """One INI section: header line, exclusive end and header name."""

    __slots__ = ("start", "end", "name")

    def __init__(self, start: int, end: int, name: str) -> None:
        self.start = start
        self.end = end
        self.name = name

    def options(self, lines: list[str]) -> dict[str, str]:
        """Top-level ``key: value`` pairs of the section body.

        >>> section = Section(0, 4, "x")
        >>> section.options(["[x]", "path: ~/a", "# note", "type: git_repo"])
        {'path': '~/a', 'type': 'git_repo'}
        """
        values: dict[str, str] = {}
        for line in lines[self.start + 1:self.end]:
            stripped = line.strip()
            if not stripped or stripped[0] in "#;":
                continue
            match = OPTION_RE.match(stripped)
            if match:
                values.setdefault(match.group(1).lower(), match.group(2).strip())
        return values


def find_sections(lines: list[str]) -> list[Section]:
    """All INI sections in order; comments and text before the first stay out.

    >>> names = [s.name for s in find_sections(["[a]", "x: 1", "# c", "[ b ] # note"])]
    >>> names
    ['a', 'b']
    """
    headers = []
    for index, line in enumerate(lines):
        match = SECTION_RE.match(line)
        if match:
            headers.append((index, match.group(1).strip()))
    sections = []
    for position, (start, name) in enumerate(headers):
        end = headers[position + 1][0] if position + 1 < len(headers) else len(lines)
        sections.append(Section(start, end, name))
    return sections


def _normalize_path(value: str) -> str:
    return os.path.normpath(os.path.expanduser(value))


def _normalize_origin(value: str) -> str:
    value = value.strip().rstrip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value.lower()


def canonical_block(
    name: str = DEFAULT_NAME,
    path: str = DEFAULT_PATH,
    origin: str = DEFAULT_ORIGIN,
    branch: str = DEFAULT_BRANCH,
    managed_services: str = DEFAULT_MANAGED_SERVICES,
    install_script: str = DEFAULT_INSTALL_SCRIPT,
) -> list[str]:
    """The canonical stanza as a list of lines, without surrounding blanks.

    >>> canonical_block()[0]
    '[update_manager vorons_configs]'
    >>> canonical_block()[-1]
    'primary_branch: main'
    >>> canonical_block(managed_services="klipper")[-1]
    'managed_services: klipper'
    """
    block = [
        "[update_manager %s]" % name,
        "type: git_repo",
        "path: %s" % path,
        "origin: %s" % origin,
        "primary_branch: %s" % branch,
    ]
    if managed_services:
        block.append("managed_services: %s" % managed_services)
    if install_script:
        block.append("install_script: %s" % install_script)
    return block


def _is_update_manager(section: Section) -> bool:
    return section.name.split(None, 1)[0].lower() == UPDATE_MANAGER_PREFIX


def _is_ours(section: Section, lines: list[str], *, name: str, target_path: str,
             target_origin: str) -> bool:
    if not _is_update_manager(section):
        return False
    if section.name.split(None, 1)[-1].strip() == name:
        return True
    options = section.options(lines)
    path = options.get("path", "")
    if path and _normalize_path(path) == target_path:
        return True
    origin = options.get("origin", "")
    return bool(origin) and _normalize_origin(origin) == target_origin


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(("#", ";"))


def _trailer_start(lines: list[str], section: Section) -> int:
    """Index of a comment block that belongs to the next section.

    A comment block separated from the section body by a blank line is usually
    the header of the next section (``# Unrelated section follows`` before
    ``[update_manager crowsnest]``), so replacing or removing the section must
    keep it.  Comments attached to the body are part of the section.
    """
    last = section.end - 1
    while last > section.start and not lines[last].strip():
        last -= 1
    if last <= section.start or not _is_comment(lines[last]):
        return section.end
    start = last
    while start > section.start + 1 and _is_comment(lines[start - 1]):
        start -= 1
    if start <= section.start + 1 or lines[start - 1].strip():
        return section.end
    return start


def _collapse_blank_runs(lines: list[str]) -> list[str]:
    """At most one blank line in a row, no trailing blanks."""
    result: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            blank = False
            result.append(line)
        elif not blank:
            blank = True
            result.append("")
    while result and not result[-1]:
        result.pop()
    return result


def ensure_text(
    text: str,
    *,
    name: str = DEFAULT_NAME,
    path: str = DEFAULT_PATH,
    origin: str = DEFAULT_ORIGIN,
    branch: str = DEFAULT_BRANCH,
    managed_services: str = DEFAULT_MANAGED_SERVICES,
    install_script: str = DEFAULT_INSTALL_SCRIPT,
) -> tuple[str, bool]:
    """Canonical text and whether it differs from ``text``.

    >>> text, changed = ensure_text("[server]\\nhost: 0.0.0.0\\n")
    >>> changed, "[update_manager vorons_configs]" in text
    (True, True)
    >>> ensure_text(text)[1]
    False
    """
    lines = text.splitlines()
    target_path = _normalize_path(path)
    target_origin = _normalize_origin(origin)
    block = canonical_block(name, path, origin, branch, managed_services, install_script)
    sections = find_sections(lines)
    ours = [
        section for section in sections
        if _is_ours(section, lines, name=name, target_path=target_path,
                    target_origin=target_origin)
    ]

    if not ours:
        kept = _collapse_blank_runs(lines)
        if kept:
            kept.append("")
        kept.extend(block)
        new_lines = kept
    else:
        first = ours[0]
        first_core_end = _trailer_start(lines, first)
        trailer = lines[first_core_end:first.end]
        dropped: set[int] = set()
        for section in ours[1:]:
            trailer_start = _trailer_start(lines, section)
            # Keep the blank line in front of a trailer: it separates the
            # canonical block from the comment block of the next section.
            end = trailer_start - 1 if trailer_start < section.end else section.end
            dropped.update(range(section.start, end))
        kept = []
        for index, line in enumerate(lines):
            if index == first.start:
                kept.extend(block)
                if trailer:
                    kept.append("")
                    kept.extend(trailer)
            elif first.start < index < first_core_end:
                continue
            elif first_core_end <= index < first.end:
                continue
            elif index in dropped:
                continue
            else:
                kept.append(line)
        new_lines = _collapse_blank_runs(kept)

    new_text = "\n".join(new_lines) + "\n" if new_lines else ""
    return new_text, new_text != text


def write_text(path: str, text: str) -> None:
    """Atomic replace that keeps the mode of an existing file."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    handle, temporary = tempfile.mkstemp(prefix=".moonraker.", dir=directory, text=True)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        if os.path.exists(path):
            os.chmod(temporary, stat.S_IMODE(os.stat(path).st_mode))
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def apply_ensure(config_path: str, *, dry_run: bool = False, **options: str) -> str:
    """Ensure the entry in ``config_path``; returns the status word."""
    path = os.path.expanduser(config_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as stream:
            original = stream.read()
    elif dry_run:
        original = ""
    else:
        raise FileNotFoundError(path)
    text, changed = ensure_text(original, **options)
    if not changed:
        return "unchanged"
    if dry_run:
        return "would update"
    write_text(path, text)
    return "updated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure the canonical [update_manager vorons_configs] entry.")
    commands = parser.add_subparsers(dest="command")
    ensure = commands.add_parser("ensure", help="upsert the canonical entry")
    ensure.add_argument("--config", required=True,
                        help="moonraker.conf to edit (required)")
    ensure.add_argument("--name", default=DEFAULT_NAME, help="section name suffix")
    ensure.add_argument("--path", default=DEFAULT_PATH, help="git checkout path")
    ensure.add_argument("--origin", default=DEFAULT_ORIGIN, help="repository URL")
    ensure.add_argument("--branch", default=DEFAULT_BRANCH, help="primary branch")
    ensure.add_argument("--managed-services", default=DEFAULT_MANAGED_SERVICES,
                        help="services Moonraker restarts (empty to omit)")
    ensure.add_argument("--install-script", default=DEFAULT_INSTALL_SCRIPT,
                        help="install_script path (empty to omit)")
    ensure.add_argument("--dry-run", action="store_true",
                        help="print the result, change nothing")
    commands.add_parser("selftest", help="run the offline fixtures")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "selftest":
        return selftest()
    if args.command != "ensure":
        parser.print_usage(sys.stderr)
        print("ERROR: command is required (ensure or selftest)", file=sys.stderr)
        return 2
    options = {
        "name": args.name,
        "path": args.path,
        "origin": args.origin,
        "branch": args.branch,
        "managed_services": args.managed_services,
        "install_script": args.install_script,
    }
    path = os.path.expanduser(args.config)
    try:
        status = apply_ensure(path, dry_run=args.dry_run, **options)
    except FileNotFoundError:
        print("ERROR: %s does not exist; deploy moonraker.conf first" % path,
              file=sys.stderr)
        return 1
    except OSError as error:
        print("ERROR: cannot write %s: %s" % (path, error), file=sys.stderr)
        return 1
    print("%s: %s" % (status, path))
    return 0


# --- Offline selftest -------------------------------------------------------


def selftest() -> int:
    """Exercise the text upsert and the file round trip (no printer)."""
    failures = 0

    def check(label: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        if condition:
            print("ok: %s" % label)
            return
        print("FAILED: %s%s" % (label, ": " + detail if detail else ""))
        failures += 1

    base = "[server]\nhost: 0.0.0.0\n\n[update_manager]\nchannel: dev\n"
    canonical = "\n".join(canonical_block())

    text, changed = ensure_text(base)
    check("missing entry appended", changed)
    check("appended entry is complete",
          "type: git_repo" in text and "primary_branch: main" in text
          and "managed_services" not in text and "install_script" not in text)

    text, changed = ensure_text(base + "\n" + canonical + "\n")
    check("canonical entry is a no-op", not changed)

    duplicates = base + "\n" + "\n".join([
        "[update_manager voron_standart_configs]",
        "type: git_repo",
        "path: ~/vorons_configs",
        "origin: https://github.com/spectrespc/vorons_configs",
        "primary_branch: main",
        "managed_services: klipper",
        "#install_script: tools/install.sh",
        "",
        "[update_manager voron_personal_configs]",
        "type: git_repo",
        "path: ~/vorons_configs_local",
        "origin: https://github.com/spectrespc/vorons_configs.git",
        "primary_branch: main",
        "managed_services: klipper",
        "",
        "[update_manager belay]",
        "type: git_repo",
        "path: ~/belay_klippy_module",
        "origin: https://github.com/Annex-Engineering/Belay.git",
        "managed_services: klipper",
        "",
    ])
    text, changed = ensure_text(duplicates)
    check("duplicates collapsed", changed and text.count("[update_manager vorons_configs]") == 1)
    check("legacy entries removed",
          "voron_standart_configs" not in text and "voron_personal_configs" not in text)
    check("custom section kept",
          "[update_manager belay]" in text and "~/belay_klippy_module" in text)
    canonical_section = [
        section for section in find_sections(text.splitlines())
        if section.name == "update_manager vorons_configs"
    ][0]
    canonical_options = canonical_section.options(text.splitlines())
    check("canonical block has no services or install script",
          "managed_services" not in canonical_options
          and "install_script" not in canonical_options)
    check("duplicate section comment removed",
          "#install_script: tools/install.sh" not in text)
    check("collapse is idempotent", not ensure_text(text)[1])

    stale = base + "\n".join([
        "",
        "# Config repository (hand-written note)",
        "[update_manager vorons_configs]",
        "type: git_repo",
        "path: ~/vorons_configs",
        "origin: https://github.com/spectrespc/vorons_configs",
        "primary_branch: main",
        "#install_script: tools/install.sh",
        "",
        "# Unrelated section follows",
        "[update_manager crowsnest]",
        "type: git_repo",
        "path: ~/crowsnest",
        "",
    ])
    text, changed = ensure_text(stale)
    check("stale entry normalized", changed)
    stale_options = {
        section.name: section.options(text.splitlines())
        for section in find_sections(text.splitlines())
    }["update_manager vorons_configs"]
    check("canonical options only",
          "primary_branch" in stale_options
          and "managed_services" not in stale_options
          and "install_script" not in stale_options)
    check("comments preserved",
          "# Config repository (hand-written note)" in text
          and "# Unrelated section follows" in text)
    check("stale comment dropped", "#install_script: tools/install.sh" not in text)

    with tempfile.TemporaryDirectory() as directory:
        config = os.path.join(directory, "moonraker.conf")
        with open(config, "w", encoding="utf-8") as stream:
            stream.write(base)
        check("file run reports update", apply_ensure(config) == "updated")
        with open(config, encoding="utf-8") as stream:
            written = stream.read()
        check("file has the canonical entry",
              "primary_branch: main" in written
              and "install_script" not in written)
        check("second file run is unchanged", apply_ensure(config) == "unchanged")
        with open(config, "w", encoding="utf-8") as stream:
            stream.write(base)
        check("dry run reports the change", apply_ensure(config, dry_run=True) == "would update")
        with open(config, encoding="utf-8") as stream:
            check("dry run wrote nothing", stream.read() == base)
        missing = os.path.join(directory, "absent.conf")
        check("dry run accepts a missing file",
              apply_ensure(missing, dry_run=True) == "would update")
        try:
            apply_ensure(missing)
        except FileNotFoundError:
            check("missing file is an error", True)
        else:
            check("missing file is an error", False)

    print("moonraker_conf selftest: %s" % ("FAILED" if failures else "ok"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())