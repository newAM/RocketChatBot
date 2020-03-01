#!/usr/bin/env python3.8

import time
import os
import re
import asyncio
import random
from typing import Optional
from args import arg

from rocketchatbot import RocketChatBot
from rocketchat_data import Message
from owo import owo
from random_excuse import random_excuse
from util import get_file_by_name

DIR = os.path.dirname(os.path.realpath(__file__))
MEME_DIR = os.path.join(DIR, "memes")
MEME_EXTS = (".png", ".gif", ".jpg", ".jpeg")
MEME_NAME_CHARS = "-_.abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
MEME_NAME_LEN = 64

app = RocketChatBot()
MEME_ROOMS = ["GENERAL"]

LINUX_NO_GNU = re.compile(
    r"^(?:(?!gnu).)*linux(?:(?!gnu).)*$", flags=re.IGNORECASE | re.DOTALL
)


@app.cmd("ping", help="pong")
async def ping(message: Message) -> str:
    return "pong"


@app.match(LINUX_NO_GNU, rate_limit=7 * 24 * 3600)
async def linux_gnu(message: Message) -> str:
    return (
        "I'd just like to interject for a moment. "
        "What you're referring to as Linux, is in fact, GNU/Linux, "
        "or as I've recently taken to calling it, GNU plus Linux. "
        "Linux is not an operating system unto itself, "
        "but rather another free component of a fully functioning GNU system "
        "made useful by the GNU corelibs, "
        "shell utilities and vital system components comprising a full OS "
        "as defined by POSIX.\n"
        "Many computer users run a modified version of the GNU system every day, "
        "without realizing it. "
        "Through a peculiar turn of events, "
        'the version of GNU which is widely used today is often called "Linux", '
        "and many of its users are not aware that it is basically the GNU system, "
        "developed by the GNU Project.\n"
        "There really is a Linux, "
        "and these people are using it, "
        "but it is just a part of the system they use. "
        "Linux is the kernel: the program in the system that allocates the machine's "
        "resources to the other programs that you run. "
        "The kernel is an essential part of an operating system, "
        "but useless by itself; "
        "it can only function in the context of a complete operating system. "
        "Linux is normally used in combination with the GNU operating system: "
        "the whole system is basically GNU with Linux added, or GNU/Linux. "
        'All the so-called "Linux" distributions are really distributions of GNU/Linux.'
    )


@app.cmd(
    "timer",
    args=[arg("duration", type=int, help="duration in seconds")],
    help="set an egg timer",
)
async def timer(message: Message) -> str:
    if message.args.duration > 600:
        return "duration cannot be more than 600s"
    elif message.args.duration < 0:
        return "duration cannot be less than 0s"

    await asyncio.sleep(message.args.duration)
    return f"Your {message.args.duration}s timer is up @{str(message.user.name)}!"


@app.cmd(
    "spam", args=[arg("text", type=str, help="text to spam")], help="spams some text",
)
async def spam(message: Message) -> str:
    coros = []
    for _ in range(5):
        coros.append(app.send_message(message.room_id, message.args.text))
    asyncio.gather(*coros)


@app.cmd("pong", help="ping")
async def pong(message: Message) -> str:
    return "ping"


@app.cmd(
    "owo",
    args=[arg("text", type=str, help="text to translate")],
    help="translates text to owo",
)
async def owo_handler(message: Message) -> str:
    return owo(message.args.text)


@app.cmd("uptime", help="display uptime")
async def uptime(message: Message) -> str:
    uptime = time.time() - app.start_time
    timestamp = time.strftime("%Hh %Mm %Ss", time.gmtime(uptime))
    return "Uptime: " + timestamp


@app.cmd("do", args=[arg("anything", help="thing to do")], help="does anything")
async def excuse(message: Message) -> str:
    return random_excuse()


@app.cmd("saymyname", help="says your name")
async def saymyname(message: Message) -> str:
    return "@" + message.username


@app.cmd(
    "say", args=[arg("text", type=str, help="text to say")], help="says some text",
)
async def say(message: Message) -> str:
    return message.args.text


@app.cmd(
    "feedback",
    args=[arg("text", type=str, help="text to give as feedback")],
    help="give feedback",
)
async def feedback(message: Message) -> str:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    feedback = ""
    for line in message.args.text.splitlines():
        feedback += f"[{timestamp}] [{str(message.user.name)}] "
        feedback += line
        feedback += "\n"
    with open("feedback.txt", "a", newline="") as f:
        f.write(feedback)

    return f"Thanks for the feedback @{str(message.user.name)}!"


@app.cmd("hcf", help="halt and catch fire")
async def hcf(message: Message):
    return f"@{str(message.user.name)} is not authorized for this function."


@app.cmd("listmemes", help="lists all memes", rooms=MEME_ROOMS)
async def listmemes(message: Message) -> str:
    ret = "**Meme Menu**:\n```"
    for meme in os.listdir(MEME_DIR):
        ret += f"{str(meme)}\n"
    ret += "```"
    return ret


@app.cmd("randmeme", help="get a random meme", rooms=MEME_ROOMS)
async def randmeme(message: Message):
    meme = os.path.join(MEME_DIR, random.choice(os.listdir(MEME_DIR)))
    await app.upload_file(message.room_id, meme)


@app.cmd(
    "meme",
    args=[arg("meme", type=str, help="name of meme")],
    help="get a specific meme from listmemes",
    rooms=MEME_ROOMS,
)
async def meme(message: Message) -> Optional[str]:

    meme = get_file_by_name(os.listdir(MEME_DIR), message.args.meme)
    if meme is None:
        return f"Invalid meme: `{str(message.args.meme)}`"
    else:
        meme = os.path.join(MEME_DIR, meme)
        await app.upload_file(message.room_id, meme)


@app.cmd(
    "newmeme",
    help="add a new meme (use this command in the description of a image)",
    rooms=MEME_ROOMS,
)
async def newmeme(message: Message) -> Optional[str]:
    if not message.attachments:
        return "no image attachment found"

    num_attachments = len(message.attachments)
    if num_attachments > 1:
        return f"found {num_attachments} attachments, expected 1"

    attachment = message.attachments[0]

    if attachment.title.endswith(MEME_EXTS):
        return f"memes are only accepted in these formats: `{MEME_EXTS}`"

    if len(attachment.title) > MEME_NAME_LEN:
        return f"meme file name must be less than {MEME_NAME_LEN} chars long"

    for char in attachment.title:
        if char not in MEME_NAME_CHARS:
            return f"file name may only contain these characters: {MEME_NAME_CHARS}"

    if get_file_by_name(os.listdir(MEME_DIR), message.attachment_title) is not None:
        return "meme with the same name already exists"

    try:
        await app.download_attachments(message, MEME_DIR)
    except Exception:
        msg = "failed to download attachment"
        app.logger.exception(msg)
        return msg
    else:
        return f"Added `{message.attachment_title}` to the meme bank."


if __name__ == "__main__":
    app.run(
        username="bot", password="12345", hostname="10.0.0.4", port=3000, ssl=False,
    )
