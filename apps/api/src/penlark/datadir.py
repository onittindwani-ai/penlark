"""Where the demo data folder (seed/, eval/, ...) lives.

Only a source checkout has the data folder next to the code. An installed copy (the Docker image) does not, so the folder named by
SEED_DIR (settings.seed_dir) is always the first choice and the checkout's folder is only the last resort.
"""

from __future__ import annotations

from pathlib import Path

REPO_DATA = Path(__file__).resolve().parents[4] / "data"


def data_dir(seed_dir: str | Path | None = None, fallback: Path | None = None) -> Path:
    """The folder that holds seed/authors.json. Says plainly when it cannot be found."""
    fallback = REPO_DATA if fallback is None else fallback
    if seed_dir:
        found = Path(seed_dir)
    elif (fallback / "seed" / "authors.json").is_file():
        found = fallback
    else:
        raise FileNotFoundError("The demo data folder was not found. Set SEED_DIR to the folder that holds seed/authors.json.")
    if not (found / "seed" / "authors.json").is_file():
        raise FileNotFoundError(f"There is no seed/authors.json in the demo data folder {found}. Check SEED_DIR.")
    return found


def data_dir_or_none(seed_dir: str | Path | None = None, fallback: Path | None = None) -> Path | None:
    try:
        return data_dir(seed_dir, fallback)
    except FileNotFoundError:
        return None
