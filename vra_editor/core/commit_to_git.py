import getpass
import hashlib
import logging
import shutil
from pathlib import Path
from typing import Optional

from dulwich import porcelain
from dulwich.config import ConfigFile
from dulwich.diff_tree import CHANGE_DELETE, tree_changes
from dulwich.repo import Repo

from ..app_data import BOOTSTRAP_DIR, get_git_dir
from ..config import load_locations

_GITFILE_NAME = ".git"

# Where fallback commits go when the primary repo (app_data.get_git_dir(),
# which can be a network share -- see Settings' "Application Data" field)
# is unreachable. Always under BOOTSTRAP_DIR, never itself configurable,
# so the fallback can't suffer the same outage as the thing it's a
# fallback for.
_FALLBACK_ROOT = BOOTSTRAP_DIR / "fallback_git"


def git_author_identity() -> bytes:
    """OS login username, in the 'Name <email>' form dulwich requires.
    There's no real email to give it, so a synthetic localhost address
    stands in -- only the name half is meaningful here."""
    uname = getpass.getuser()
    return f"{uname} <{uname}@localhost>".encode()


def _archive_repo_root(file_path: Path):
    """The working-tree root for the archive's version history:
      - the common parent of 'edit' and 'reviewed', if they share one
        (so both locations' history lives in a single repo), else
      - whichever of 'edit'/'reviewed' actually contains file_path.
    None if neither applies."""
    locations = {
        key: Path(value).resolve()
        for key, value in load_locations().items()
        if key in ('edit', 'reviewed')
    }
    parents = {loc.parent for loc in locations.values()}

    if len(parents) == 1 and file_path.is_relative_to(next(iter(parents))):
        return next(iter(parents))
    for root in locations.values():
        if file_path.is_relative_to(root):
            return root
    return None


def _set_core_worktree(control_dir: Path, work_tree: Path) -> None:
    config_path = control_dir / "config"
    config = ConfigFile.from_path(str(config_path))
    config.set((b"core",), b"worktree", str(work_tree).encode())
    config.write_to_path(str(config_path))


def _open_or_init_repo(work_tree: Path) -> Repo:
    """Opens the archive's git history, kept under this app's own
    GIT_DIR (see app_data.py) rather than inside the archive itself --
    the same 'separate git dir' layout `git init --separate-git-dir`
    produces (verified readable by the real git CLI too), so the
    archive folder only ever gets a small .git *pointer file*, never
    real git metadata of its own.
    """
    gitfile = work_tree / _GITFILE_NAME
    if gitfile.is_file():
        return Repo(str(work_tree))

    git_dir = get_git_dir()
    legacy_git_dir = work_tree / _GITFILE_NAME  # same name, but a directory under the old layout
    git_dir.parent.mkdir(parents=True, exist_ok=True)

    if legacy_git_dir.is_dir():
        # A repo from before this app kept its own clutter separate --
        # move its history across rather than abandoning it.
        shutil.move(str(legacy_git_dir), str(git_dir))
    elif not git_dir.exists():
        porcelain.init(str(git_dir))
        # porcelain.init(git_dir) nests a .git inside it, making git_dir
        # its own working tree -- flatten that so git_dir itself holds
        # objects/refs/HEAD/config directly, the layout a separate git
        # dir needs.
        nested = git_dir / _GITFILE_NAME
        for item in nested.iterdir():
            shutil.move(str(item), str(git_dir / item.name))
        nested.rmdir()

    gitfile.write_text(f"gitdir: {git_dir}\n")
    _set_core_worktree(git_dir, work_tree)
    return Repo(str(work_tree))


def _commit(repo: Repo, file_path: Path, message: str, **commit_kwargs) -> None:
    """Adds and commits file_path (already written to disk, somewhere
    under repo's working tree) into repo. commit_kwargs lets a replay
    pass through the original author/timestamp (see _replay_fallback)
    instead of stamping the current user/time."""
    porcelain.add(repo, [str(file_path)])
    identity = commit_kwargs.pop('author', None) or git_author_identity()
    porcelain.commit(repo, message, author=identity, committer=identity, **commit_kwargs)


def _fallback_root(repo_path: Path) -> Path:
    """A stable, always-local repo for fallback commits, one per
    distinct archive repo root (in practice there's just one -- the
    shared edit/reviewed parent -- but this keys on it rather than
    assuming that, in case that ever changes)."""
    key = hashlib.sha1(str(repo_path).encode()).hexdigest()[:12]
    return _FALLBACK_ROOT / key


def _commit_to_fallback(repo_path: Path, file_path: Path, message: str) -> Optional[str]:
    """Records file_path's current content into the fallback repo,
    mirroring its path relative to repo_path -- a fully self-contained
    repo (its own working tree, not the real archive), since the real
    archive's own .git pointer can only point at one git-dir at a time
    (see _open_or_init_repo) and swapping that back and forth would
    risk leaving it pointed at the wrong one. _replay_fallback() is what
    later turns this into real primary-repo history."""
    fallback_root = _fallback_root(repo_path)
    try:
        fallback_root.mkdir(parents=True, exist_ok=True)
        if not (fallback_root / _GITFILE_NAME).exists():
            porcelain.init(str(fallback_root))

        relative = file_path.relative_to(repo_path)
        staged_path = fallback_root / relative
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, staged_path)

        repo = Repo(str(fallback_root))
        try:
            _commit(repo, staged_path, message)
        finally:
            repo.close()
        return 'fallback'
    except Exception as e:
        logging.error(f"Could not record {file_path} to the local fallback repo either: {e}")
        return None


def _replay_fallback(repo_path: Path, primary_repo: Repo) -> None:
    """Opportunistically called every time the primary repo opens
    successfully: replays any commits _commit_to_fallback stashed while
    it was unreachable, in the order they were made, preserving each
    one's original author and timestamp.

    Replaying means temporarily writing each historical snapshot into
    the *real* archive file so primary_repo can commit it -- since
    that's the same working tree a scholar might be actively editing,
    every path this function touches gets its real, current content
    backed up first and restored in `finally` no matter what happens,
    so a replay can never be how a user's actual file content changes,
    only how the primary repo's history catches up.

    Never raises -- a failed replay is logged and retried on the next
    successful commit; it must not block the new commit that triggered
    this call.
    """
    fallback_root = _fallback_root(repo_path)
    if not (fallback_root / _GITFILE_NAME).exists():
        return

    fallback_repo = Repo(str(fallback_root))
    backups: dict[Path, Optional[bytes]] = {}
    replayed = 0
    total = 0
    try:
        commits = list(fallback_repo.get_walker())  # newest first
        total = len(commits)
        commits.reverse()  # oldest first, so primary's history gains them in the order they happened

        for entry in commits:
            commit = entry.commit
            parent_tree = fallback_repo[commit.parents[0]].tree if commit.parents else None
            changes = tree_changes(fallback_repo.object_store, parent_tree, commit.tree)
            for change in changes:
                if change.type == CHANGE_DELETE or change.new is None or change.new.path is None:
                    continue
                relative = Path(change.new.path.decode())
                dest = repo_path / relative
                if dest not in backups:
                    backups[dest] = dest.read_bytes() if dest.exists() else None
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(fallback_repo[change.new.sha].data)
                _commit(
                    primary_repo, dest, commit.message.decode(errors='replace'),
                    author=commit.author,
                    author_timestamp=commit.author_time, author_timezone=commit.author_timezone,
                    commit_timestamp=commit.commit_time, commit_timezone=commit.commit_timezone,
                )
            replayed += 1
    except Exception as e:
        logging.error(f"Replaying fallback history for {repo_path} failed after {replayed}/{total} commit(s): {e}")
    finally:
        fallback_repo.close()
        for dest, original in backups.items():
            if original is None:
                dest.unlink(missing_ok=True)
            else:
                dest.write_bytes(original)

    if total and replayed == total:
        shutil.rmtree(fallback_root)
        logging.info(f"Replayed {replayed} fallback commit(s) into the primary repo for {repo_path}")
    elif total:
        logging.warning(f"Only replayed {replayed}/{total} fallback commit(s) for {repo_path} -- will retry later")


def add_file_to_repo(tgt, message) -> Optional[str]:
    """Commits `tgt` (an absolute path to a file under the 'edit' or
    'reviewed' location) to a shared dulwich repo, so edits and
    approvals share one audit trail. The repo's actual git metadata
    lives under this app's own clutter folder (app_data.GIT_DIR), not
    inside the archive.

    If that clutter folder is unreachable (e.g. a network share that's
    offline), the commit is recorded to an always-local fallback repo
    instead, and replayed into the primary repo automatically the next
    time it's reachable -- see _commit_to_fallback / _replay_fallback.
    Any failure touching the primary repo triggers this, not just an
    obvious OSError -- dulwich's Repo() resolves the .git pointer
    file's target lazily, so an unreachable target doesn't necessarily
    fail there; it can just as easily surface later, from
    porcelain.add/commit, as a KeyError or another non-OSError type
    depending on exactly how it's unreachable.

    Returns 'primary' or 'fallback' depending on which one actually
    recorded it, so a caller can tell a scholar apart from the (rare)
    total-failure case -- None -- where nothing was recorded anywhere.
    """
    file_path = Path(tgt).resolve()
    repo_path = _archive_repo_root(file_path)

    if repo_path is None:
        logging.error(f"Could not determine a version-control repo location for {file_path}")
        return None

    try:
        repo = _open_or_init_repo(repo_path)
        try:
            _replay_fallback(repo_path, repo)
            _commit(repo, file_path, message)
            return 'primary'
        finally:
            repo.close()
    except Exception as e:
        logging.warning(
            f"Primary version-control repo unavailable ({e}) -- "
            f"recording {file_path} to the local fallback instead"
        )
        return _commit_to_fallback(repo_path, file_path, message)
