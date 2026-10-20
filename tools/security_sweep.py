"""A focused security sweep of the repository.

Checks for the common injection and disclosure vectors and prints a
report.  It is a development aid, not a substitute for a proper review.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {
    "node_modules",
    ".next",
    ".git",
    "__pycache__",
    ".pytest_cache",
    "data",
    "dist",
    "out",
    ".venv",
    "venv",
}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".mjs", ".yml", ".yaml", ".sql", ".json", ".md"}


def source_files() -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [name for name in dirnames if name not in SKIP]
        for filename in filenames:
            path = Path(dirpath) / filename
            if path.suffix.lower() in TEXT_SUFFIXES:
                found.append(path)
    return found


def sweep(label: str, files: list[Path], regexes: tuple[str, ...]) -> int:
    count = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for regex in regexes:
                if re.search(regex, line):
                    relative = path.relative_to(ROOT)
                    print(f"  {relative}:{number}  {line.strip()[:130]}".encode("ascii", "replace").decode("ascii"))
                    count += 1
    print(f"{label}: {count} match(es)\n")
    return count


def main() -> int:
    print("=" * 74)
    print("SECURITY SWEEP")
    print("=" * 74)

    files = source_files()
    print(f"Scanning {len(files)} source files.\n")

    total = 0

    total += sweep(
        "Committed credentials (Dsn / key literals)",
        files,
        (
            r"https://[a-f0-9]{32,}@",
            r"sk-[A-Za-z0-9]{20,}",
            r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}",
            r"(?i)(api_key|secret|password|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]",
        ),
    )

    total += sweep(
        "Dynamic code execution",
        files,
        (r"\beval\s*\(", r"\bexec\s*\(", r"os\.system\s*\(", r"os\.popen\s*\(", r"subprocess\."),
    )

    total += sweep(
        "Raw SQL string building",
        files,
        (
            r"f\"[^\"]*\b(SELECT|INSERT|UPDATE|DELETE)\b",
            r"\.format\([^\)]*\).*\b(SELECT|INSERT|UPDATE|DELETE)\b",
        ),
    )

    total += sweep(
        "Shell invocation with a variable",
        files,
        (r"shell\s*=\s*True", r"execSync\s*\(", r"spawnSync\s*\(.*shell"),
    )

    total += sweep(
        "Client-side use of a server-only variable",
        files,
        (r"NEXT_PUBLIC_[A-Z_]*(KEY|SECRET|PASSWORD|TOKEN|SERVICE_ROLE)",),
    )

    total += sweep(
        "Unvalidated redirect target",
        files,
        (r"redirect\([^)]*searchParams", r"NextResponse\.redirect\([^)]*searchParams"),
    )

    total += sweep(
        "Dangerous HTML injection",
        files,
        (r"dangerouslySetInnerHTML",),
    )

    total += sweep(
        "Wildcard CORS",
        files,
        (r"allow_origins\s*=\s*\[\s*[\"']\*[\"']\s*\]",),
    )

    print("=" * 74)
    print(f"TOTAL MATCHES: {total}")
    print("Each match must be reviewed: some are legitimate (a test fixture,")
    print("a comment, a local development default).")
    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
