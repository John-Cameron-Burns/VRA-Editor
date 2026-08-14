"""Checks whether a newer release is available, against the public
VRA-Editor-releases repo's GitHub API -- a separate, public repo the
private source repo's release workflow also publishes to (see
.github/workflows/build-release.yml), specifically so this needs no
authentication and works for anyone running the app, not just people
with access to the private repo.
"""

import json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import certifi

RESOURCES_DIR = Path(__file__).resolve().parent.parent / "resources"
_RELEASES_API_URL = "https://api.github.com/repos/ztz88f5f6h-glitch/VRA-Editor-releases/releases/latest"
_USER_AGENT = "VRA-Editor-update-check"

# Same rationale as authority_lookup.py's own _SSL_CONTEXT: an explicit
# CA bundle rather than the host Python's own SSL config, which a
# python.org macOS install in particular can ship without until its
# "Install Certificates.command" is run by hand.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

DEV_BUILD_VERSION = "development build"


class UpdateCheckError(Exception):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str


def get_app_version() -> str:
    """This build's own version -- read from a plain text file
    PyInstaller bundles in at build time (see packaging/VRA_Editor.spec,
    which writes it from the same VRA_EDITOR_VERSION the .app/.exe/.deb
    themselves are versioned from). The source tree itself never
    carries this file, so running from source -- or a build where that
    packaging step didn't run -- both fall back the same way, and
    check_for_update() treats that fallback as "nothing to compare",
    not a version older than everything."""
    version_file = RESOURCES_DIR / "VERSION"
    if version_file.is_file():
        text = version_file.read_text().strip()
        if text:
            return text
    return DEV_BUILD_VERSION


def _parse_version(v: str) -> tuple:
    """A numeric sort key so '1.10.0' correctly compares greater than
    '1.9.0' (plain string comparison wouldn't). Falls back to (0,) for
    anything that doesn't parse as dotted integers, so an unexpected
    tag shape never crashes the comparison -- it just never counts as
    newer than a real version."""
    parts = []
    for piece in v.split('.'):
        try:
            parts.append(int(piece))
        except ValueError:
            return (0,)
    return tuple(parts) if parts else (0,)


def check_for_update(timeout: float = 5.0) -> Optional[UpdateInfo]:
    """None if already current (including: this is a development build,
    which has nothing meaningful to compare against). Raises
    UpdateCheckError on any network/API failure -- unlike
    authority_lookup.py's search(), which is always user-triggered, this
    is also called silently at startup, so it's the *caller's* job to
    decide whether a failure here is worth surfacing (see
    main_window.py's _check_for_updates: silent at startup, shown when
    the user explicitly clicked Check for Updates)."""
    current = get_app_version()
    if current == DEV_BUILD_VERSION:
        return None

    req = urllib.request.Request(
        _RELEASES_API_URL,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as e:
        raise UpdateCheckError(str(e)) from e

    latest_tag = payload.get("tag_name", "")
    latest_version = latest_tag[1:] if latest_tag.startswith("v") else latest_tag
    if not latest_version:
        raise UpdateCheckError("Release feed didn't include a version tag.")

    if _parse_version(latest_version) <= _parse_version(current):
        return None
    return UpdateInfo(version=latest_version, url=payload.get("html_url", _RELEASES_API_URL))
