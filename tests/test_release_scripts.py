from __future__ import annotations

import re
import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _pyproject_version() -> str:
    text = (_repo_root() / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
    assert match, "Failed to find [project].version in pyproject.toml"
    return match.group(1)


def test_bin_version_current_matches_pyproject() -> None:
    out = subprocess.check_output(
        ["bash", "bin/version", "--current"],
        cwd=_repo_root(),
        text=True,
    ).strip()
    assert out == _pyproject_version()


def test_bin_version_patch_dry_run_bumps_patch() -> None:
    major, minor, patch = map(int, _pyproject_version().split("."))
    expected = f"{major}.{minor}.{patch + 1}"

    out = subprocess.check_output(
        ["bash", "bin/version", "patch", "--dry-run"],
        cwd=_repo_root(),
        text=True,
    ).strip()

    assert out == expected

