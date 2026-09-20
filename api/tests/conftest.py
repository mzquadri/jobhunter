from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.settings import Profile

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def profile() -> Profile:
    """The shipped example profile. Tests run against what the repo publishes,
    so a broken example is caught here rather than by the next person to clone."""
    with (REPO_ROOT / "config" / "profile.example.yml").open(encoding="utf-8") as fh:
        return Profile(yaml.safe_load(fh))
