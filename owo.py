import re


OWO_REPLACE = {"you": "yuw", "and": "awnd", "lol": "lawl"}
WHITESPACE_SPLIT = re.compile(r"(\s+)")


def owo(text: str):
    """ Adapted from owotrans. """
    ret = ""
    for word in WHITESPACE_SPLIT.split(text):
        upper = word.isupper()
        if word.lower() in OWO_REPLACE:
            word = OWO_REPLACE[word.lower()]
            if upper:
                word = word.upper()
        else:
            word = word.replace("l", "w")
            word = word.replace("L", "W")
            word = word.replace("r", "w")
            word = word.replace("R", "W")

        ret += word

    return ret
