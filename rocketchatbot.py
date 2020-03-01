import asyncio
import logging
import logging.config
import inspect
import uuid
import json
import copy
import os
import re
import time
import websockets
import queue
import shlex
import aiohttp
import dataclasses
from typing import Optional, List, NamedTuple
from typing import Callable
from typing import Union
from typing import Pattern
from rocketchat_data import Message
from args import ArgumentParser
from args import arg


class _Command(NamedTuple):
    """
    Command object.

    Args:
        coro: Coroutine callable for the command.
        help: Help text.
        args: Arguments for the command.
        rooms: Whitelist of rooms to allow this command in.
    """

    coro: Callable
    help: str
    args: Optional[List[arg]]
    rooms: Optional[List[str]]


@dataclasses.dataclass
class _Match:
    """
    Match object.

    Args:
        coro: Coroutine callable for the match.
        rate_limit: Rate limit for the match.
    """

    coro: Callable
    pattern: Pattern
    rate_limit: Optional[int]
    last_called: Optional[int] = None


class RocketChatBot:
    """
    Application class.

    Args:
        log_config: override default logging config
        prefix: prefix for all bot commands
    """

    ENCODING = "UTF-8"

    LOGGING_CONFIG_DEFAULTS = {
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

    def __init__(self, log_config: Optional[dict] = None, prefix: str = "!"):
        logging.config.dictConfig(log_config or self.LOGGING_CONFIG_DEFAULTS)
        self.logger = logging.getLogger(__name__)
        self.prefix = prefix
        self.start_time = time.time()
        self._completion_event = {}
        self._completion = {}
        self._commands = {}
        self._match = []

    def run(
        self,
        username: str,
        password: str,
        hostname: str,
        *,
        port: Optional[int] = None,
        ssl=None,
    ):
        """
        Start execution of the bot.

        Args:
            username: username for the account to run the bot
            password: password for the assoicated username
            hostname: hostname or IPv4 of the RocketChat server
            port: RocketChat server port
            ssl: SSL context to utilize
        """
        self.username = username
        self.password = password
        self.hostname = hostname.strip("/")
        self.port = port
        self._ssl = ssl
        self._session = None

        port_str = f":{self.port}" if port is not None else ""

        self._ws_url = f"wss://{self.hostname}{port_str}/websocket"
        s = "s" if ssl is None else ""
        self._http_url = f"http{s}://{self.hostname}{port_str}"
        self._rest_url = f"{self._http_url}/api/v1"

        asyncio.run(self._bootstrap())

    async def _bootstrap(self):
        """ Starts the bot. """
        self._write_queue = asyncio.Queue()
        self._chat_queue = asyncio.Queue()
        self._connected = asyncio.Event()
        async with websockets.client.connect(
            self._ws_url, ssl=self._ssl
        ) as ws, aiohttp.ClientSession() as session:
            self._session = session
            write_task = asyncio.create_task(self._write_loop(ws))
            read_task = asyncio.create_task(self._read_loop(ws))
            chat_task = asyncio.create_task(self._chat_loop())

            async def ws_bootstrap():
                # open the connection
                await self._send_msg(
                    "connect", {"version": "1", "support": ["1"]}, noid=True
                )
                await self._connected.wait()

                # login
                await self._method(
                    "login", user={"username": self.username}, password=self.password,
                )

                # subscribe to all messages
                await self._msg(
                    "sub",
                    {
                        "name": "stream-room-messages",
                        "params": ["__my_messages__", True],
                    },
                )

            async def rest_bootstap():
                async with self._session.post(
                    url=f"{self._rest_url}/login",
                    data={"user": self.username, "password": self.password},
                    ssl=self._ssl,
                ) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        self.logger.error(text)
                    data = json.loads(text)

                self._headers = {
                    "X-Auth-Token": data["data"]["authToken"],
                    "X-User-Id": data["data"]["userId"],
                }

            try:
                await asyncio.gather(
                    rest_bootstap(), ws_bootstrap(), write_task, read_task, chat_task,
                )
            except Exception:
                self.logger.exception("failed to gather tasks")
                return

    def get_argument_parser(self, room_id: str) -> ArgumentParser:
        """
        Gets the argument parser for a given room.

        Args:
            room_id: Room id.

        Returns:
            ArgumentParser object for the room.
        """
        parser = ArgumentParser(prog=self.prefix, description="Rocket.Chat bot")
        subparsers = parser.add_subparsers(help="commands")
        for command_flag, command in self._commands.items():
            if command.rooms is None or room_id in command.rooms:
                subparser = subparsers.add_parser(command_flag, help=command.help)
                for a in command.args:
                    subparser.add_argument(a.name, type=a.type, help=a.help)

        return parser

    def validate_args(self, coro: Callable):
        """
        Validates the arguments of a decorated function.

        Args:
            coro: Coroutine function to check

        Raises:
            ValueError:
                Decorated function is missing arguments.
        """
        coro_args = list(inspect.signature(coro).parameters.keys())
        if not coro_args:
            raise ValueError(
                "Required argument `message` missing " f"in the {coro.__name__}() cmd?"
            )

    def match(self, pattern: Union[str, Pattern], rate_limit: Optional[int] = None):
        if isinstance(pattern, str):
            pattern = re.compile(pattern)

        def response(coro: Callable) -> Callable:
            self.validate_args(coro)
            self._match.append(
                _Match(coro=coro, pattern=pattern, rate_limit=rate_limit)
            )
            return coro

        return response

    def cmd(
        self,
        command: str,
        args: Optional[List[arg]] = None,
        help: Optional[str] = None,
        rooms: Optional[List[str]] = None,
    ):
        """
        Decorator to register a coroutine as a command.

        Args:
            command: Command without prefix.
            args: Command arguments.
            help: Text to display upon a help command.
            rooms: Whitelist of rooms to allow the command on.

        Raises:
            ValueError:
                Request argument missing from decorated function,
                or multiple handlers defined for one command.
        """
        if args is None:
            args = []

        def response(coro: Callable) -> Callable:
            self.validate_args(coro)

            if command in self._commands:
                raise ValueError(f"Multiple handlers defined for {command}")

            self._commands[command] = _Command(
                coro=coro, rooms=rooms, help=help, args=args
            )

            return coro

        return response

    async def _write_loop(self, ws):
        """ Writes to the websocket. """
        try:
            while True:
                data = await self._write_queue.get()
                log_data = json.dumps(data)
                if len(log_data) > 80:
                    log_data = json.dumps(data, indent=4)
                self.logger.debug(f"[WRITE] {log_data}")
                await ws.send(json.dumps(data))
        except Exception:
            self.logger.exception("write loop died")
            raise

    async def _read_loop(self, ws):
        """ Reads from the websocket. """
        try:
            while True:
                raw_data = await ws.recv()
                data = json.loads(raw_data)
                if len(raw_data) < 80:
                    log_data = data
                else:
                    log_data = json.dumps(data, indent=4)

                self.logger.debug(f"[READ ] {log_data}")

                try:
                    msg = data["msg"]
                except KeyError:
                    continue

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
                    try:
                        collection = data["collection"]
                        event_name = data["fields"]["eventName"]
                    except KeyError:
                        continue

                    if (
                        collection == "stream-room-messages"
                        and event_name == "__my_messages__"
                    ):
                        await self._chat_queue.put(data)
                    else:
                        self.logger.debug("nope")
        except Exception:
            self.logger.exception("read loop died")
            raise

    async def _chat_loop(self):
        """ Handles chatbot commands. """
        try:
            pending = [asyncio.create_task(self._chat_queue.get())]
            while True:
                done, pending = await asyncio.wait(
                    pending, return_when=asyncio.FIRST_COMPLETED
                )

                for task in done:
                    result = task.result()
                    if isinstance(result, dict):
                        pending.add(asyncio.create_task(self._chat_task(result)))
                        pending.add(asyncio.create_task(self._chat_queue.get()))
        except Exception:
            self.logger.exception("chat loop died")
            raise

    async def _chat_task(self, data: dict):
        """ Handles chat messages. """
        try:
            msg = Message(data["fields"]["args"])
            if (
                msg.username == self.username
                or msg.edited_at is not None
                or msg.reactions
            ):
                return

            for match in self._match:
                if match.pattern.match(msg.text):
                    if match.rate_limit is not None:
                        if match.last_called is None:
                            elapsed = float("inf")
                        else:
                            elapsed = time.monotonic() - match.last_called

                        remaining = match.rate_limit - elapsed

                        if remaining > 0:
                            self.logger.debug(f"rate limited, {remaining:.3f}s left")
                            return

                    match.last_called = time.monotonic()
                    try:
                        response = await match.coro(msg)
                    except Exception:
                        self.logger.exception("failed to handle match")
                    else:
                        if response is not None:
                            await self.send_message(msg.room_id, response)

            if msg.text.startswith(self.prefix):
                parser = self.get_argument_parser(msg.room_id)

                async def send_enqueued_messages() -> int:
                    num_messages = 0
                    while True:
                        try:
                            message = parser.msg_q.get_nowait()
                            num_messages += 1
                        except queue.Empty:
                            break
                        else:
                            await self.send_message(msg.room_id, f"```\n{message}```")

                    return num_messages

                text = msg.text[len(self.prefix) :]
                args = shlex.split(text)
                command = args[0]

                if command == "help":
                    parser.print_help()
                    await send_enqueued_messages()
                    return
                else:
                    try:
                        msg.args = parser.parse_args(args)
                    except Exception as e:
                        if not await send_enqueued_messages():
                            await self.send_message(
                                msg.room_id, str(e),
                            )
                        return
                    else:
                        await send_enqueued_messages()

                coro = self._commands[command].coro
                try:
                    response = await coro(msg)
                except Exception:
                    self.logger.exception("failed to handle command")
                else:
                    if response is not None:
                        await self.send_message(msg.room_id, response)
        except Exception:
            self.logger.exception("failed to handle message")

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
        await self._method("sendMessage", _id=message_id, rid=room_id, msg=message)
        return message_id

    async def _method(self, method: str, **kwargs) -> dict:
        """ Performs a method call. """
        return await self._msg("method", {"method": method, "params": [{**kwargs}]})

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

        with open(file, "rb") as f:
            payload = {"file": f}
            async with self._session.post(
                url=f"{self._rest_url}/rooms.upload/{room_id}",
                data=payload,
                headers=self._headers,
                ssl=self._ssl,
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    self.logger.debug(text)
                    resp.raise_for_status()

    async def download_attachments(self, message: Message, directory: str):
        """
        Downloads messages from the chat.

        Args:
            message: message to download from
            directory: directory to download into

        Raises:
            aiohttp.ClientResponseError: request failed
        """
        async with self._session.get(
            f"{self._http_url}{message.image_url}",
            headers=self._headers,
            ssl=self._ssl,
        ) as resp:
            if resp.status != 200:
                self.logger.error(f"Unexpected response code: {resp.status}")
                resp.raise_for_status()
            else:
                path = os.path.join(directory, message.attachment_title)
                with open(path, "wb") as f:
                    f.write(await resp.read())
