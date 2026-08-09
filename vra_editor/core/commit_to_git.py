import getpass
import logging
from pathlib import Path

from ..config import load_locations

from dulwich import porcelain


def git_author_identity() -> bytes:
    """OS login username, in the 'Name <email>' form dulwich requires.
    There's no real email to give it, so a synthetic localhost address
    stands in -- only the name half is meaningful here."""
    uname = getpass.getuser()
    return f"{uname} <{uname}@localhost>".encode()


def add_file_to_repo(tgt, message) -> bool:
    """Commits `tgt` (an absolute path to a file under the 'edit' or
    'reviewed' location) to a shared dulwich repo, so edits and
    approvals share one audit trail.

    Repo root is:
      - the common parent of 'edit' and 'reviewed', if they share one
        (so both locations' history lives in a single repo), else
      - whichever of 'edit'/'reviewed' actually contains `tgt`.
    """
    file_path = Path(tgt).resolve()
    locations = {
        key: Path(value).resolve()
        for key, value in load_locations().items()
        if key in ('edit', 'reviewed')
    }
    parents = {loc.parent for loc in locations.values()}

    repo_path = None
    if len(parents) == 1 and file_path.is_relative_to(next(iter(parents))):
        repo_path = next(iter(parents))
    else:
        for root in locations.values():
            if file_path.is_relative_to(root):
                repo_path = root
                break

    if repo_path is None:
        logging.error(f"Could not determine a version-control repo location for {file_path}")
        return False

    # Create and open the repo if it doesn't exist. repo_path is the
    # edit/reviewed folder (or their common parent) itself -- it
    # already exists and already has files in it, so init just adds
    # a .git alongside them.
    if not (repo_path / ".git").is_dir():
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = porcelain.init(str(repo_path))
    else:
        try:
            repo = porcelain.open_repo(str(repo_path))
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
