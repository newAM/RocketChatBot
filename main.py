#!/usr/bin/env python3.7

import time
import os
import random
from typing import Optional

from rocketchatbot import RocketChatBot, ChatMessage
from owo import owo
from random_excuse import random_excuse

DIR = os.path.dirname(os.path.realpath(__file__))
MEME_DIR = os.path.join(DIR, "memes")
MEME_LIST = os.listdir(MEME_DIR)
MEME_EXTS = (".png", ".gif", ".jpg")
MEME_NAME_CHARS = "-_.abcdefghijklmnopqrstuvwxyz0123456789"
MEME_NAME_LEN = 64

app = RocketChatBot()


@app.cmd("ping", help="pong")
async def ping(message: ChatMessage) -> str:
    return "pong"


@app.cmd("owo", args=["text"], help="translates text to owo")
async def owo_handler(message: ChatMessage) -> str:
    return owo(message.command_body)


@app.cmd("uptime", help="display uptime")
async def uptime(message: ChatMessage) -> str:
    """ ``!uptime`` command. """
    uptime = time.time() - app.start_time
    timestamp = time.strftime("%Hh %Mm %Ss", time.gmtime(uptime))
    return "Uptime: " + timestamp


@app.cmd("do", args=["anything"], help="does anything")
async def excuse(message: ChatMessage) -> str:
    return random_excuse()


@app.cmd("saymyname", help="says your name")
async def saymyname(message: ChatMessage) -> str:
    return "@" + message.username


@app.cmd("say", args=["text"], help="says some text")
async def say(message: ChatMessage) -> str:
    return message.command_body


@app.cmd("feedback", args=["text"], help="give feedback")
async def feedback(message: ChatMessage) -> str:
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    feedback = ""
    for line in message.command_body.splitlines():
        feedback += f"[{timestamp}] [{str(message.username)}] "
        feedback += line
        feedback += "\n"
    with open("feedback.txt", "a", newline="") as f:
        f.write(feedback)

    return f"Thanks for the feedback @{str(message.username)}!"


@app.cmd("help", help="display all commands")
async def help(message: ChatMessage) -> str:
    help_msg = "```\n"
    for key, value in sorted(app.handlers.items()):
        print(value)
        help_msg += f"!{key} "
        for arg in value.args:
            help_msg += f"[{arg}] "
        help_msg += f"- {value.help}\n"
    help_msg += "```"
    return help_msg


@app.cmd("hcf", help="halt and catch fire")
async def hcf(message: ChatMessage):
    return f"@{str(message.username)} is not authorized for this function."


@app.cmd("listmemes", help="lists all memes")
async def listmemes(message: ChatMessage) -> str:
    ret = "**Meme Menu**:\n```"
    for meme in MEME_LIST:
        ret += f"{str(meme)}\n"
    ret += "```"
    return ret


@app.cmd("randmeme", help="lists all memes")
async def randmeme(message: ChatMessage):
    meme = os.path.join(MEME_DIR, random.choice(MEME_LIST))
    await app.upload_file(message.room_id, meme)


@app.cmd("meme", args=["meme"], help="get a specific meme from listmemes")
async def meme(message: ChatMessage) -> Optional[str]:
    if message.command_body not in MEME_LIST:
        return f"Invalid meme: `{str(message.command_body)}`"
    else:
        meme = os.path.join(MEME_DIR, message.command_body)
        await app.upload_file(message.room_id, meme)


@app.cmd(
    "newmeme",
    help="add a new meme (use this command in the description of a image)",
)
async def newmeme(message: ChatMessage) -> Optional[str]:
    if not message.has_image_attachment:
        return "no image attachment found"

    if not message.attachment_title.endswith(MEME_EXTS):
        return f"memes are only accepted in these formats: `{MEME_EXTS}`"

    if len(message.attachment_title) > MEME_NAME_LEN:
        return f"meme file name must be less than {MEME_NAME_LEN} chars long"

    for char in message.attachment_title:
        if char not in MEME_NAME_CHARS:
            return (
                f"file name may only contain these characters: "
                f"{MEME_NAME_CHARS}"
            )

    if message.attachment_title in MEME_LIST:
        return "meme with the same name already exists"

    try:
        await app.download_attachments(message, MEME_DIR)
    except Exception:
        msg = "failed to download attachment"
        app.logger.exception(msg)
        return msg
    else:
        return f"Added `{message.attachment_title}` to the meme bank."


# add rate limiting

if __name__ == "__main__":
    app.run(
        username="bot",
        password="pass",
        hostname="10.0.0.4",
        port=3000,
        ssl=False,
    )
