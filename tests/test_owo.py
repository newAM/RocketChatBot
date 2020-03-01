import pytest
from ..owo import owo


@pytest.mark.parametrize(
    "text, expected", [("```\nlol\n```", "```\nlawl\n```")]
)
def test_owo(text: str, expected: str):
    assert owo(text) == expected
