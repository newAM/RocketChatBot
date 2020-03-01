import pytest
import bot


@pytest.mark.parametrize(
    "text, match",
    [
        ("", False),
        ("linux", True),
        ("LINUX", True),
        ("aaalinux", True),
        ("linuxaaa", True),
        ("a\nalinuxa\na", True),
        ("linuxgnu", False),
        ("l i n u x", False),
        ("linux\ngnu", False),
        ("gnu\nlinux", False),
    ],
)
def test_gnu_linux_re(text: str, match: bool):
    assert bool(bot.LINUX_NO_GNU.match(text)) == match
