from __future__ import annotations
import websockets
import aiohttp
import asyncio
import json
import uuid
import copy
import os
import logging
import logging.config
import dataclasses
import time
import random
from typing import Optional, List, Coroutine
from random_excuse import random_excuse


DIR = os.path.dirname(os.path.realpath(__file__))
START_TIME = time.time()


async def ping(rc: RocketChat, msg: ChatMessage):
    """ ``!ping`` command. """
    await rc.send_message(msg.room_id, "pong")


async def saymyname(rc: RocketChat, msg: ChatMessage):
    """ ``!saymyname`` command. """
    return await rc.send_message(msg.room_id, f"@{msg.username}")


async def say(rc: RocketChat, msg: ChatMessage):
    """ ``!say`` command. """
    await rc.send_message(msg.room_id, msg.command_body)


async def feedback(rc: RocketChat, msg: ChatMessage):
    """ ``!feedback`` command. """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())
    feedback = ""
    for line in msg.message.splitlines():
        feedback += f"[{timestamp}] [{msg.username}] {line}\n"
    with open("feedback.txt", "a", newline="") as f:
        f.write(feedback)
    await rc.send_message(
        msg.room_id, f"Thanks for the feedback @{msg.username}!"
    )


async def uptime(rc: RocketChat, msg: ChatMessage):
    """ ``!uptime`` command. """
    uptime = time.time() - START_TIME
    timestamp = time.strftime("%H:%M:%S", time.gmtime(uptime))
    await rc.send_message(msg.room_id, f"Uptime: {timestamp}")


async def excuse(rc: RocketChat, msg: ChatMessage):
    """ ``!do`` command. """
    excuse = random_excuse()
    await rc.send_message(msg.room_id, excuse)


async def help(rc: RocketChat, msg: ChatMessage):
    """ ``!help`` command. """
    help_msg = "```\n"
    for command, chat_func in CHAT_FUNCTIONS.items():
        help_msg += f"!{command} "
        for arg in chat_func.args:
            help_msg += f"[{arg}] "
        help_msg += f"- {chat_func.help}\n"
    help_msg += "```"

    await rc.send_message(msg.room_id, help_msg)


async def hcf(rc: RocketChat, msg: ChatMessage):
    """ ``!hcf`` command. """
    await rc.send_message(
        msg.room_id, f"@{msg.username} is not authorized for this function."
    )


async def randimg(rc: RocketChat, msg: ChatMessage):
    """ ``!randimg`` command. """
    image_dir = os.path.join(DIR, "images")
    random_image = os.path.join(
        image_dir, random.choice(os.listdir(image_dir))
    )
    await rc.upload_file(msg.room_id, random_image)


class ChatMessage:
    """
    Chat message dataclass.

    Args:
        data: Message data
    """

    def __init__(self, data: dict):
        self._data = data

    @property
    def collection(self) -> str:
        """ Stream collection. """
        return self._data["collection"]

    @property
    def event_name(self) -> str:
        """ Name of the event. """
        return self._data["fields"]["eventName"]

    @property
    def message(self) -> str:
        """ Message contents. """
        return self._data["fields"]["args"][0]["msg"]

    @property
    def room_id(self) -> str:
        """ Backend room id (rid). """
        return self._data["fields"]["args"][0]["rid"]

    @property
    def timestamp(self) -> int:
        """
        Timestamp of the message expressed as seconds since the epoch.
        """
        return self._data["fields"]["args"][0]["ts"]["$date"]

    @property
    def last_modified(self) -> int:
        """
        Timestamp of the last message modification
        expressed as seconds since the epoch.
        """
        return self._data["fields"]["args"][0]["_updatedAt"]["$date"]

    @property
    def username(self) -> str:
        """ Username of the user who posted the message. """
        return self._data["fields"]["args"][0]["u"]["username"]

    @property
    def is_command(self) -> bool:
        """ Returns ``True`` if the message is a bot command. """
        return self.message.startswith("!")

    @property
    def command(self) -> str:
        """ Chat command. """
        return self.message.lstrip("!").split()[0]

    @property
    def command_body(self):
        """ Body of the command without the command itself. """
        try:
            return self.message.split(" ", 1)[1]
        except IndexError:
            return ""

    @property
    def command_args(self) -> List[str]:
        """ Chat command arguments. """
        try:
            return self.message.lstrip("!").split()[1:]
        except IndexError:
            return []


@dataclasses.dataclass
class ChatFunction:
    """
    Chat function dataclass.

    Args:
        help: function help
        args: function arguments
        coro: coroutine callback
    """

    help: str
    args: List[str]
    coro: Coroutine


# Chatbot functionality.
CHAT_FUNCTIONS = {
    "do": ChatFunction(help="do anything", args=["anything"], coro=excuse),
    "feedback": ChatFunction(
        help="give feedback", args=["text"], coro=feedback
    ),
    "hcf": ChatFunction(help="halt and catch fire", args=[], coro=hcf),
    "help": ChatFunction(help="show this", args=[], coro=help),
    "ping": ChatFunction(help="pong", args=[], coro=ping),
    "randimg": ChatFunction(help="random image", args=[], coro=randimg),
    "say": ChatFunction(help="says some text", args=["text"], coro=say),
    "saymyname": ChatFunction(help="says your name", args=[], coro=saymyname),
    "uptime": ChatFunction(help="show uptime", args=[], coro=uptime),
}


class RocketChat:
    """ Utilizes the RocketChat realtime API. """

    def __init__(self, domain: str, username: str, password: str):
        self.username = username
        self.password = password
        self.domain = domain.strip("/")
        self._ws_uri = f"wss://{domain}/websocket"
        self._completion_event = {}
        self._completion = {}
        self.logger = logging.getLogger(__name__)

    async def loop_forever(self):
        """ Main coroutine to call. """
        self._write_queue = asyncio.Queue()
        self._chat_queue = asyncio.Queue()
        self._connected = asyncio.Event()
        async with websockets.client.connect(self._ws_uri, ssl=False) as ws:
            write_task = asyncio.create_task(self._write_loop(ws))
            read_task = asyncio.create_task(self._read_loop(ws))
            chat_task = asyncio.create_task(self._chat_loop())

            await self._connect()

            await self._method(
                "login",
                user={"username": self.username},
                password=self.password,
            )

            await self._msg(
                "sub",
                {
                    "name": "stream-room-messages",
                    "params": ["__my_messages__", True],
                },
            )

            await asyncio.gather(write_task, read_task, chat_task)

    async def _connect(self):
        """ Connects to the websocket. """
        await self._send_msg(
            "connect", {"version": "1", "support": ["1"]}, noid=True
        )
        await self._connected.wait()

    async def _write_loop(self, ws):
        """ Writes to the websocket. """
        while True:
            data = await self._write_queue.get()
            self.logger.debug(f"[WRITE] {data}")
            await ws.send(json.dumps(data))

    async def _read_loop(self, ws):
        """ Reads from the websocket. """
        while True:
            data = json.loads(await ws.recv())

            try:
                msg = data["msg"]
            except KeyError:
                pass
            else:
                if msg == "ping":
                    await self._send_msg("pong", noid=True)
                elif msg == "connected":
                    self._connected.set()
                elif msg == "result":
                    msg_id = data["id"]
                    self._completion[msg_id] = data["result"]
                    self._completion_event[msg_id].set()
                elif msg == "nosub":
                    msg_id = data["id"]
                    self._completion[msg_id] = None
                    self._completion_event[msg_id].set()
                elif msg == "changed":
                    await self._chat_queue.put(data)

            self.logger.debug(f"[READ ] {data}")

    async def _chat_loop(self):
        """ Handles chatbot commands. """
        while True:
            data = await self._chat_queue.get()
            msg = ChatMessage(data)

            if (
                msg.collection == "stream-room-messages"
                and msg.event_name == "__my_messages__"
                and msg.is_command
            ):
                try:
                    coro = CHAT_FUNCTIONS[msg.command].coro
                except KeyError:
                    continue
                else:
                    try:
                        await coro(self, msg)
                    except Exception:
                        self.logger.exception("something went wrong")

    async def send_message(self, room_id: str, message: str) -> str:
        """
        Posts a chat message to the room.

        Args:
            room_id: room identifier
            message: message contents

        Returns:
            Message id.
        """
        message_id = str(uuid.uuid4())
        await self._method(
            "sendMessage", _id=message_id, rid=room_id, msg=message
        )
        return message_id

    async def _method(self, method: str, **kwargs) -> dict:
        """ Performs a method call. """
        return await self._msg(
            "method", {"method": method, "params": [{**kwargs}]}
        )

    async def _get_msg(self, msg_id: str) -> dict:
        """ Gets the result of a message. """
        await self._completion_event[msg_id].wait()
        del self._completion_event[msg_id]
        ret = copy.deepcopy(self._completion[msg_id])
        del self._completion[msg_id]
        return ret

    async def _send_msg(
        self, msg: str, data: Optional[dict] = None, *, noid: bool = False
    ) -> Optional[str]:
        """
        Sends a message.

        Args:
            msg: message type
            data: message data
            noid:
                ``True`` to skip ID generation.
                Used for non-standard messages such as ``"connect"``.

        Returns:
            Generated message ID.
        """
        if data is None:
            data = {}
        payload = {"msg": msg, **data}

        if noid:
            msg_id = None
        else:
            msg_id = str(uuid.uuid4())
            payload["id"] = msg_id
            self._completion_event[msg_id] = asyncio.Event()

        await self._write_queue.put(payload)

        return msg_id

    async def _msg(self, *args, **kwargs) -> dict:
        """ Sends a message and gets the result. """
        msg_id = await self._send_msg(*args, **kwargs)
        return await self._get_msg(msg_id)

    async def upload_file(self, room_id: str, file: str):
        """
        Uploads a file to the room.
        Unfortunately uses the REST API since file upload
        is not yet support by the realtime API.

        Args:
            room_id: backend room id
            file: path to file

        Raises:
            aiohttp.ClientResponseError: request failed
            FileNotFoundError: invalid file path
        """
        if not os.path.isfile(file):
            raise FileNotFoundError(f"no file found at {file}")
        base_api_url = f"http://{self.domain}/api/v1"
        login_uri = f"{base_api_url}/login"
        upload_uri = f"{base_api_url}/rooms.upload/{room_id}"
        login_payload = {"user": self.username, "password": self.password}
        async with aiohttp.ClientSession() as session:
            async with session.post(
                login_uri, data=login_payload, ssl=False
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    self.logger.debug(text)
                    resp.raise_for_status()
                data = json.loads(text)

            headers = {
                "X-Auth-Token": data["data"]["authToken"],
                "X-User-Id": data["data"]["userId"],
            }

            with open(file, "rb") as f:
                payload = {"file": f}
                async with session.post(
                    upload_uri, headers=headers, data=payload, ssl=False
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        self.logger.debug(text)
                        resp.raise_for_status()


async def main():
    config = {
        "version": 1,
        "formatters": {
            "simple": {
                "class": "logging.Formatter",
                "format": "[{asctime}] [{levelname: <8}] {message}",
                "style": "{",
            }
        },
        "handlers": {
            "console": {
                "level": "DEBUG",
                "class": "logging.StreamHandler",
                "formatter": "simple",
            }
        },
        "root": {"level": "DEBUG", "handlers": ["console"]},
    }
    logging.config.dictConfig(config)

    domain = "10.0.0.4:3000"
    rc = RocketChat(domain, "bot", "pass")
    await rc.loop_forever()


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
