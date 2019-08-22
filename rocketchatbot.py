import asyncio
import logging
import logging.config
import inspect
import uuid
import json
import copy
import os
import time
import websockets
import aiohttp
from typing import Optional, List, Coroutine, NamedTuple


class ChatMessage:
    """
    Chat message dataclass.

    Args:
        data: message data
        prefix: command prefix
    """

    def __init__(self, data: dict, prefix: str):
        self._data = data
        self._prefix = prefix

    @property
    def collection(self) -> str:
        """ Stream collection. """
        return self._data["collection"]

    @property
    def event_name(self) -> str:
        """ Name of the event. """
        return self._data["fields"]["eventName"]

    @property
    def _args(self):
        """ Message arguments. """
        return self._data["fields"]["args"][0]

    @property
    def message(self) -> str:
        """ Message contents. """
        return self._args["msg"]

    @property
    def file_type(self) -> Optional[str]:
        """ File type, if it exists. """
        try:
            return self._args["file"]["type"]
        except KeyError:
            return None

    @property
    def has_image_attachment(self) -> bool:
        try:
            return self.file_type.startswith("image")
        except Exception:
            return False

    @property
    def attachment_description(self) -> Optional[str]:
        """ Attachment description, if it exists. """
        try:
            return self._args["attachments"][0]["description"]
        except KeyError:
            return None

    @property
    def attachment_title(self) -> Optional[str]:
        """ Attachment title, if it exists. """
        try:
            return self._args["attachments"][0]["title"]
        except KeyError:
            return None

    @property
    def image_url(self):
        """ Image URL. """
        return self._args["attachments"][0]["image_url"]

    @property
    def room_id(self) -> str:
        """ Backend room id (rid). """
        return self._args["rid"]

    @property
    def timestamp(self) -> int:
        """
        Timestamp of the message expressed as seconds since the epoch.
        """
        return self._args["ts"]["$date"]

    @property
    def last_modified(self) -> int:
        """
        Timestamp of the last message modification
        expressed as seconds since the epoch.
        """
        return self._args["_updatedAt"]["$date"]

    @property
    def username(self) -> str:
        """ Username of the user who posted the message. """
        return self._args["u"]["username"]

    @property
    def is_command(self) -> bool:
        """ Returns ``True`` if the message is a bot command. """
        try:
            attach_cmd = self.attachment_description.startswith(self._prefix)
        except AttributeError:
            attach_cmd = False

        return self.message.startswith(self._prefix) or attach_cmd

    @property
    def command(self) -> str:
        """ Chat command. """
        if self.message.startswith(self._prefix):
            return self.message.lstrip(self._prefix).split()[0]
        else:
            return self.attachment_description.lstrip(self._prefix).split()[0]

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
            return self.message.lstrip(self._prefix).split()[1:]
        except IndexError:
            return []

    @property
    def reactions(self) -> List[str]:
        """ Reactions on the comment. """
        try:
            return self._args["reactions"].keys()
        except KeyError:
            return []

    @property
    def edited_at(self) -> Optional[int]:
        """
        Epoch time of the last comment edit,
        or ``None`` if the comment has not been edited.
        """
        try:
            return self._args["editedAt"]["$date"]
        except KeyError:
            return None


class _Handler(NamedTuple):
    """
    Command Handler.

    Args:
        args: command arguments
        help: text to display upon a help command
        coro: coroutine to execute on a new command
    """

    args: Optional[List[str]]
    help: Optional[str]
    coro: Coroutine


class RocketChatBot:
    """
    Application class.

    Args:
        log_config: override default logging config
        prefix: prefix for all bot commands
    """

    ENCODING = "ASCII"

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
        self.handlers = {}
        self._completion_event = {}
        self._completion = {}

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
        s = "s" if ssl else ""
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
                    "login",
                    user={"username": self.username},
                    password=self.password,
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
                await asyncio.gather(rest_bootstap(), ws_bootstrap())
            except Exception:
                self.logger.exception("bootstrap failed")
                raise

            try:
                await asyncio.gather(write_task, read_task, chat_task)
            except Exception:
                self.logger.exception("failed to gather tasks")
                return

    def _rest_login(self, session: aiohttp.ClientSession):
        """ Logs into the rest API. """

    def cmd(
        self,
        command: str,
        args: Optional[List[str]] = None,
        help: Optional[str] = None,
    ):
        """
        Decorator to register a coroutine as a command.

        Args:
            command: command without prefix
            args: command arguments
            help: text to display upon a help command

        Raises:
            ValueError:
                Request argument missing from decorated function,
                or multiple handlers defined for one command.
        """
        if args is None:
            args = []

        def response(coro: Coroutine):
            coro_args = list(inspect.signature(coro).parameters.keys())

            if not coro_args:
                raise ValueError(
                    "Required argument `message` missing "
                    f"in the {coro.__name__}() cmd?"
                )

            if command in self.handlers:
                raise ValueError(f"Multiple handlers defined for {command}")

            self.handlers[command] = _Handler(args=args, help=help, coro=coro)

            return coro

        return response

    async def _write_loop(self, ws):
        """ Writes to the websocket. """
        try:
            while True:
                data = await self._write_queue.get()
                self.logger.debug(f"[WRITE] {data}")
                await ws.send(json.dumps(data))
        except Exception:
            self.logger.exception("write loop died")
            raise

    async def _read_loop(self, ws):
        """ Reads from the websocket. """
        try:
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
        except Exception:
            self.logger.exception("write loop died")
            raise

    async def _chat_loop(self):
        """ Handles chatbot commands. """
        try:
            while True:
                data = await self._chat_queue.get()
                msg = ChatMessage(data, self.prefix)

                if (
                    msg.collection == "stream-room-messages"
                    and msg.event_name == "__my_messages__"
                    and msg.is_command
                    and not msg.reactions
                    and msg.username != self.username
                    and msg.edited_at is None
                ):
                    try:
                        coro = self.handlers[msg.command].coro
                    except KeyError:
                        await self.send_message(
                            msg.room_id,
                            f"invalid command: `{str(msg.command)}`",
                        )
                    else:
                        try:
                            msg.command_body.encode(self.ENCODING, "strict")
                        except Exception:
                            await self.send_message(
                                msg.room_id,
                                f"I am on a strict diet of "
                                f"{self.ENCODING} bytes.",
                            )
                            continue

                        try:
                            response = await coro(msg)
                        except Exception:
                            self.logger.exception("failed to handle command")
                        else:
                            if response is not None:
                                await self.send_message(msg.room_id, response)
        except Exception:
            self.logger.exception("chat loop died")
            raise

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

    async def download_attachments(self, message: ChatMessage, directory: str):
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
