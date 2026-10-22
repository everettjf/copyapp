"""Resolve copy-job paths without creating files or selecting an implicit resume."""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from copyapp.source_root import source_root


def copy_paths(bundle: str, *, workspace: Optional[Path] = None,
               output_dir: Optional[Path] = None, output: Optional[Path] = None,
               project: Optional[Path] = None, resume: bool = False):
    workspace = (workspace or source_root()).resolve(strict=True)
    if output is not None and output_dir is not None:
        raise ValueError("use --output-dir or --out, not both")
    if resume and output is None and output_dir is None:
        raise ValueError("--resume requires the previous --output-dir or --out; no latest job is selected")
    if output is not None:
        if project is None:
            raise ValueError("legacy --out requires --project; use --output-dir for a combined job directory")
        evidence = output.resolve()
    else:
        if output_dir is None:
            label = re.sub(r"[^A-Za-z0-9._-]+", "-", bundle).strip(".-")[:80] or "app"
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            output_dir = workspace / "output" / f"{label}-{stamp}-{uuid.uuid4().hex}"
        root = output_dir.resolve()
        evidence = root / "evidence"
        project = project if project is not None else root / "project"
    project = project.resolve()
    if (not workspace.is_dir() or not evidence.is_relative_to(workspace) or
            not project.is_relative_to(workspace) or evidence == project or
            evidence in project.parents or project in evidence.parents):
        raise ValueError("workflow output and independent project must be separate workspace paths")
    return workspace, evidence, project
