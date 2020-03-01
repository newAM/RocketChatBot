from .. import util
import pytest
from typing import Optional
from typing import List


@pytest.mark.parametrize(
    "filename, result",
    [("/a/a.b", "a"), ("A", "a"), ("A.B.C", "a.b"), ("", "")],
)
def test_normalize_filename(filename: str, result: str):
    assert util.normalize_filename(filename) == result


@pytest.mark.parametrize(
    "files, file, result",
    [
        ([], "", None),
        (["FiLe.ExT"], "file", "FiLe.ExT"),
        (["filee", "FiLe.ExT", "filee"], "file", "FiLe.ExT"),
        (["filename", "FILE"], "file", "FILE"),
    ],
)
def test_get_file_by_name(files: List[str], file: str, result: Optional[str]):
    assert util.get_file_by_name(files, file) == result
