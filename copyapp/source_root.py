"""Locate the Copy APP checkout for optional tools not shipped in the wheel."""

import os
from pathlib import Path


def source_root() -> Path:
    """Use an explicit checkout for wheels, or the containing checkout for editable installs."""
    configured = os.environ.get("COPYAPP_SOURCE_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve(strict=True)
        if not ((root / "pyproject.toml").is_file() and
                (root / "scripts" / "bootstrap-macos.sh").is_file()):
            raise ValueError("COPYAPP_SOURCE_ROOT is not a Copy APP source checkout")
        return root
    return Path(__file__).resolve().parents[1]
