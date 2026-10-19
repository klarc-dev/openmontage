"""Canonical repository paths — single source of truth.

The projects root is the most load-bearing path in the system: checkpoints
are written under it, tool events are attributed against it, and the Backlot
board watches it. Define it once.

Every root below defaults to the source checkout, so a plain clone behaves
exactly as before. Each one can be redirected with an environment variable,
which lets OpenMontage run from an external workspace (a wrapper repository,
a CI job, a read-only install) without editing its tree:

==============================  ===========================================
Variable                        Default
==============================  ===========================================
``OPENMONTAGE_PROJECTS_DIR``    ``<home>/projects``
``OPENMONTAGE_CONFIG``          ``<home>/config.yaml``
``OPENMONTAGE_ENV_FILE``        ``<home>/.env``
``OPENMONTAGE_STYLES_PATH``     (empty) extra style dirs, searched first
``OPENMONTAGE_PIPELINE_DIRS``   (empty) extra pipeline_defs dirs, searched first
``OPENMONTAGE_WORK_DIR``        ``<home>`` (Backlot cache, portable runtimes)
``OPENMONTAGE_MUSIC_LIBRARY_DIR`` ``<home>/music_library``
==============================  ===========================================

``<home>`` is ``OPENMONTAGE_HOME``: the source checkout itself. It is not
configurable; it is exported so scripts and docs can refer to it.

List variables use ``os.pathsep`` (``:`` on POSIX, ``;`` on Windows). Within a
list the first directory that contains a name wins, and listed directories are
searched before the built-in ones.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OPENMONTAGE_HOME = REPO_ROOT


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _env_path_list(name: str) -> list[Path]:
    value = os.environ.get(name) or ""
    return [Path(part).expanduser() for part in value.split(os.pathsep) if part.strip()]


# Overridable for staging/screenshots/tests. Everything — checkpoint writes,
# event attribution, the Backlot board — follows the same root.
PROJECTS_DIR = _env_path("OPENMONTAGE_PROJECTS_DIR", REPO_ROOT / "projects")

# Runtime configuration and secrets.
CONFIG_PATH = _env_path("OPENMONTAGE_CONFIG", REPO_ROOT / "config.yaml")
ENV_FILE = _env_path("OPENMONTAGE_ENV_FILE", REPO_ROOT / ".env")

# Built-in content shipped with the source, plus optional external search dirs.
BUILTIN_STYLES_DIR = REPO_ROOT / "styles"
BUILTIN_PIPELINE_DEFS_DIR = REPO_ROOT / "pipeline_defs"
STYLES_PATH = _env_path_list("OPENMONTAGE_STYLES_PATH")
PIPELINE_DIRS = _env_path_list("OPENMONTAGE_PIPELINE_DIRS")

# Runtime writes that are not project outputs (caches, portable runtimes).
WORK_DIR = _env_path("OPENMONTAGE_WORK_DIR", REPO_ROOT)

MUSIC_LIBRARY_DIR = _env_path("OPENMONTAGE_MUSIC_LIBRARY_DIR", REPO_ROOT / "music_library")


def style_dirs() -> list[Path]:
    """Directories searched for style playbooks, in precedence order.

    External ``OPENMONTAGE_STYLES_PATH`` entries come first, then the built-in
    ``styles/``. Each directory's ``custom/`` subdirectory (where generated
    playbooks are saved) is searched right after that directory.
    """
    return [*STYLES_PATH, BUILTIN_STYLES_DIR]


def pipeline_dirs() -> list[Path]:
    """Directories searched for pipeline manifests, in precedence order."""
    return [*PIPELINE_DIRS, BUILTIN_PIPELINE_DEFS_DIR]
