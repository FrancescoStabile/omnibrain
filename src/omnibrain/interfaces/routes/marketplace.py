"""Marketplace routes — browse & install community Skills.

For v1 the "registry" is a JSON file hosted on GitHub.
Install = git-clone → validate manifest → copy to user skills dir.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Depends, HTTPException, Query  # type: ignore[attr-defined]
from pydantic import BaseModel  # type: ignore[attr-defined]

logger = logging.getLogger("omnibrain.marketplace")

# ═══════════════════════════════════════════════════════════════════════════
# Registry URL — points to a JSON file on GitHub
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_REGISTRY_URL = (
    "https://raw.githubusercontent.com/FrancescoStabile/omnibrain/"
    "main/marketplace/registry.json"
)


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic models
# ═══════════════════════════════════════════════════════════════════════════


class RegistrySkill(BaseModel):
    """A skill listed in the community registry."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "community"
    repo: str = ""
    downloads: int = 0
    stars: int = 0
    verified: bool = False
    icon: str = "🔧"
    category: str = "other"
    permissions: list[str] = []


class BrowseResponse(BaseModel):
    skills: list[RegistrySkill]
    total: int
    source: str = "github"


class InstallRequest(BaseModel):
    repo: str
    """Repository URL or shorthand (e.g. 'user/omnibrain-skill-foo')."""


class InstallResponse(BaseModel):
    status: str
    name: str = ""
    message: str = ""


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _fetch_registry(url: str) -> list[dict[str, Any]]:
    """Fetch the registry JSON from GitHub (or local cache fallback)."""
    import httpx

    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        return data.get("skills", [])
    except Exception as e:
        logger.warning("Failed to fetch registry from %s: %s", url, e)
        return []


def _resolve_repo_url(repo: str) -> str:
    """Normalize repo shorthand to a full git-cloneable URL."""
    if repo.startswith("http://") or repo.startswith("https://"):
        return repo
    if repo.startswith("github.com/"):
        return f"https://{repo}"
    # Assume GitHub shorthand: "user/repo"
    if "/" in repo and not repo.startswith("/"):
        return f"https://github.com/{repo}"
    return repo


def _validate_manifest(skill_dir: Path) -> dict[str, Any] | None:
    """Validate that a cloned repo contains a valid skill.yaml."""
    import yaml

    yaml_path = skill_dir / "skill.yaml"
    if not yaml_path.is_file():
        return None

    try:
        with open(yaml_path) as f:
            manifest = yaml.safe_load(f)
    except Exception:
        return None

    # Minimum required fields
    if not isinstance(manifest, dict):
        return None
    if not manifest.get("name"):
        return None

    return manifest


def _clone_and_install(repo_url: str, skills_dir: Path) -> tuple[str, str]:
    """Clone a repo into a temp dir, validate, and move to skills_dir.

    Returns (skill_name, message).
    Raises HTTPException on failure.
    """
    with tempfile.TemporaryDirectory(prefix="omnibrain-skill-") as tmp:
        tmp_path = Path(tmp) / "skill"

        # Clone
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(tmp_path)],
                check=True,
                capture_output=True,
                timeout=60,
            )
        except FileNotFoundError as e:
            raise HTTPException(
                status_code=503,
                detail={"code": "GIT_NOT_FOUND", "message": "git is not installed on the server"},
            ) from e
        except subprocess.CalledProcessError as e:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "CLONE_FAILED",
                    "message": f"Failed to clone repository: {e.stderr.decode()[:200]}",
                },
            ) from e
        except subprocess.TimeoutExpired as e:
            raise HTTPException(
                status_code=504,
                detail={"code": "CLONE_TIMEOUT", "message": "Repository clone timed out (60s)"},
            ) from e

        # Validate manifest
        manifest = _validate_manifest(tmp_path)
        if manifest is None:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "INVALID_MANIFEST",
                    "message": "Repository does not contain a valid skill.yaml",
                },
            )

        skill_name = manifest["name"]
        dest = skills_dir / skill_name

        # Check for existing skill
        if dest.exists():
            # Remove old version for upgrade
            shutil.rmtree(dest)

        # Remove .git directory to save space
        git_dir = tmp_path / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir)

        # Move into place
        shutil.move(str(tmp_path), str(dest))

        return skill_name, f"Installed {skill_name} from {repo_url}"


# ═══════════════════════════════════════════════════════════════════════════
# Route registration
# ═══════════════════════════════════════════════════════════════════════════


def register_marketplace_routes(app: Any, server: Any, verify_api_key: Any) -> None:
    """Register marketplace browse & install routes."""

    registry_url = DEFAULT_REGISTRY_URL

    @app.get("/api/v1/marketplace/browse", response_model=BrowseResponse)
    async def marketplace_browse(
        search: str = Query("", description="Search term"),
        category: str = Query("", description="Filter by category"),
        token: str = Depends(verify_api_key),
    ) -> BrowseResponse:
        """Browse community skills from the registry."""
        raw = _fetch_registry(registry_url)

        skills = []
        for item in raw:
            try:
                skill = RegistrySkill(**item)
            except Exception:
                continue

            # Filter
            if search:
                term = search.lower()
                if term not in skill.name.lower() and term not in skill.description.lower():
                    continue
            if category and skill.category != category:
                continue

            skills.append(skill)

        return BrowseResponse(skills=skills, total=len(skills))

    @app.post("/api/v1/marketplace/install", response_model=InstallResponse)
    async def marketplace_install(
        body: InstallRequest,
        token: str = Depends(verify_api_key),
    ) -> InstallResponse:
        """Install a community skill from a git repository.

        Clones the repo, validates the manifest, and moves it to the
        user's skills directory.
        """
        repo_url = _resolve_repo_url(body.repo)

        # Determine user skills directory
        data_dir: Path = server._data_dir
        skills_dir = data_dir / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)

        name, message = _clone_and_install(repo_url, skills_dir)

        # Re-discover skills if runtime is available
        runtime = getattr(server, "_skill_runtime", None)
        if runtime:
            runtime.discover([skills_dir])

        return InstallResponse(status="installed", name=name, message=message)
