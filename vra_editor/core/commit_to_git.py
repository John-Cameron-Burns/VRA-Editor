import getpass
import logging
import shutil
from pathlib import Path

from dulwich import porcelain
from dulwich.config import ConfigFile
from dulwich.repo import Repo

from ..app_data import get_git_dir
from ..config import load_locations

_GITFILE_NAME = ".git"


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


def add_file_to_repo(tgt, message) -> bool:
    """Commits `tgt` (an absolute path to a file under the 'edit' or
    'reviewed' location) to a shared dulwich repo, so edits and
    approvals share one audit trail. The repo's actual git metadata
    lives under this app's own clutter folder (app_data.GIT_DIR), not
    inside the archive.
    """
    file_path = Path(tgt).resolve()
    repo_path = _archive_repo_root(file_path)

    if repo_path is None:
        logging.error(f"Could not determine a version-control repo location for {file_path}")
        return False

    try:
        repo = _open_or_init_repo(repo_path)
    except Exception as e:
        logging.error(f"Could not open repo: {e}")
        return False

    try:
        porcelain.add(repo, [str(file_path)])
    except Exception as e:
        logging.error(f"Could not add {file_path} to repo: {e}")
        return False

    identity = git_author_identity()
    porcelain.commit(repo, message, author=identity, committer=identity)
    return True
