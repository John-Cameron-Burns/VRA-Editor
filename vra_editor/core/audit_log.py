import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dulwich.diff_tree import CHANGE_DELETE, tree_changes
from dulwich.repo import Repo

from ..config import load_locations


@dataclass(frozen=True)
class Revision:
    """One file changed in one commit of the archive's shared history
    (see core/commit_to_git.py). A single commit can in principle touch
    more than one file -- e.g. one made by hand outside this app -- so
    a Revision is per (commit, path), not per commit."""
    sha: str
    filename: str  # relative to the repo root, e.g. "edit/foo.xml"
    author: str
    date: datetime.datetime
    message: str


def _repo_root() -> Optional[Path]:
    """Same working-tree root commit_to_git.py's _archive_repo_root
    resolves to -- the common parent of the 'edit' and 'reviewed'
    locations, if they share one. None if they don't (nothing to show)."""
    locations = {
        key: Path(value).resolve()
        for key, value in load_locations().items()
        if key in ('edit', 'reviewed')
    }
    parents = {loc.parent for loc in locations.values()}
    if len(parents) == 1:
        return next(iter(parents))
    return None


def _open_repo() -> Optional[Repo]:
    root = _repo_root()
    if root is None or not (root / '.git').is_file():
        return None  # no shared location, or nothing's ever been committed
    return Repo(str(root))


def _clean_author(raw: str) -> str:
    """dulwich author strings are 'Name <email>' -- see
    commit_to_git.git_author_identity(). Only the name half is
    meaningful here, there being no real email behind it."""
    return raw.split('<')[0].strip()


def list_revisions(limit: int = 1000) -> list[Revision]:
    """Every (commit, changed file) pair in the archive's shared
    history, most recent first -- the raw material for the Audits
    dialog's table. Empty if there is no repo yet, nothing has been
    committed, or the repository is currently unreachable (e.g.
    app_data is on an offline network share).

    dulwich's Repo() resolves the .git pointer file's target lazily --
    it can succeed even when that target is gone, only failing once
    something actually tries to read from it, and not always with the
    same exception type (a missing directory fails differently than a
    stale mount). So both opening and reading are covered here, broadly,
    rather than guessing which specific exception to expect."""
    try:
        repo = _open_repo()
    except Exception as e:
        logging.warning(f"Archive history repository is unavailable: {e}")
        return []
    if repo is None:
        return []

    revisions = []
    try:
        walker = repo.get_walker(max_entries=limit)
        for entry in walker:
            commit = entry.commit
            parent_tree = None
            if commit.parents:
                parent_tree = repo[commit.parents[0]].tree
            changes = tree_changes(repo.object_store, parent_tree, commit.tree)
            for change in changes:
                # A deletion has no 'new' side -- the file doesn't exist in
                # this commit's tree at all, so there's nothing here to
                # list as a restorable revision (see read_revision_content,
                # which looks the path up in commit.tree and would just
                # fail for one of these).
                if change.type == CHANGE_DELETE or change.new is None:
                    continue
                path = change.new.path
                if path is None:
                    continue
                revisions.append(Revision(
                    sha=commit.id.decode(),
                    filename=path.decode(),
                    author=_clean_author(commit.author.decode()),
                    date=datetime.datetime.fromtimestamp(commit.commit_time),
                    message=commit.message.decode(errors='replace').strip(),
                ))
    except Exception as e:
        logging.warning(f"Archive history repository became unavailable while reading it: {e}")
        return []
    finally:
        repo.close()
    return revisions


def read_revision_content(revision: Revision) -> bytes:
    """The file's exact byte content as of that revision -- for
    restoring it into a new file (see
    DocumentController.restore_revision). Raises RuntimeError if the
    repository isn't available, for whatever reason -- see
    list_revisions's docstring on why that's caught broadly."""
    try:
        repo = _open_repo()
        if repo is None:
            raise RuntimeError("The archive's history repository is not available.")
        try:
            commit = repo[revision.sha.encode()]
            tree = repo[commit.tree]
            _mode, sha = tree.lookup_path(repo.object_store.__getitem__, revision.filename.encode())
            return repo[sha].data
        finally:
            repo.close()
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError("The archive's history repository is not available.") from e
