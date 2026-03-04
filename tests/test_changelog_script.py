from __future__ import annotations

import subprocess
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_bin_changelog_check_fails_when_unreleased_empty(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## [Unreleased]",
                "",
                "### Added",
                "",
                "### Fixed",
                "",
                "## [0.1.1] - 2026-02-22",
                "",
                "### Added",
                "- Prior release note.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    proc = subprocess.run(
        ["bash", "bin/changelog", "check", "--file", str(changelog)],
        cwd=_repo_root(),
        text=True,
        capture_output=True,
    )
    assert proc.returncode != 0
    assert "Unreleased section is empty" in (proc.stderr + proc.stdout)


def test_bin_changelog_release_moves_unreleased_into_version(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "All notable changes to this project will be documented in this file.",
                "",
                "## [Unreleased]",
                "",
                "### Added",
                "- New thing.",
                "",
                "### Fixed",
                "- Bug fix.",
                "",
                "## [0.1.1] - 2026-02-22",
                "",
                "### Added",
                "- Prior release note.",
                "",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.check_call(
        [
            "bash",
            "bin/changelog",
            "release",
            "0.1.2",
            "--date",
            "2026-02-22",
            "--file",
            str(changelog),
        ],
        cwd=_repo_root(),
    )

    updated = changelog.read_text(encoding="utf-8")

    assert "## [Unreleased]" in updated
    assert "## [0.1.2] - 2026-02-22" in updated
    assert "## [0.1.1] - 2026-02-22" in updated

    # Unreleased is reset to an empty template.
    assert "## [Unreleased]\n\n### Added\n\n### Changed\n\n### Fixed\n\n### Removed\n\n" in updated

    # Prior Unreleased content is moved under the new version.
    assert "### Added\n- New thing." in updated
    assert "### Fixed\n- Bug fix." in updated


def test_bin_changelog_release_allow_empty_creates_placeholder(tmp_path: Path) -> None:
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "\n".join(
            [
                "# Changelog",
                "",
                "## [Unreleased]",
                "",
                "### Added",
                "",
                "## [0.1.1] - 2026-02-22",
                "",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.check_call(
        [
            "bash",
            "bin/changelog",
            "release",
            "0.1.2",
            "--date",
            "2026-02-22",
            "--allow-empty",
            "--file",
            str(changelog),
        ],
        cwd=_repo_root(),
    )

    updated = changelog.read_text(encoding="utf-8")
    assert "## [0.1.2] - 2026-02-22" in updated
    assert "- No notable changes." in updated

