"""Checks that a fresh clone can be set up the way SETUP (1).md says."""
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


@pytest.mark.bug
def test_finding13_requirements_file_exists():
    """
    Finding 13. SETUP step 9 says `pip install -r requirements.txt`, but the file isn't in the repo.
    It should pin the versions that worked on your Mac, because Spark's timestamp handling
    changed between versions (see finding 9 in the report).
    """
    req = REPO / "requirements.txt"
    assert req.exists(), "requirements.txt is missing"
    text = req.read_text().lower()
    for package in ["pyarrow", "pyodbc", "python-dotenv", "pyspark"]:
        assert package in text, f"{package} is not in requirements.txt"
