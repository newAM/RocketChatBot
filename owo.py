word_replace = {"you": "yuw", "and": "awnd", "lol": "lawl"}


def owo(text: str):
    """ Adapted from owotrans. """
    words = text.split()
    for i in range(0, len(words)):
        word = words[i]
        if word in word_replace:
            words[i] = word_replace[word]
            text = " ".join(words)

    text = text.replace("l", "w")
    text = text.replace("r", "w")

    return text
