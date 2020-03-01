from typing import Optional, List


class User:
    """ User object. """

    def __init__(self, data: dict):
        self._data = data

    @property
    def id(self):
        """ User identification. """
        return self._data["_id"]

    @property
    def name(self):
        """ Username of the user. """
        return self._data["username"]


class File:
    """ File uploaded with the message. """

    def __init__(self, data: dict):
        self._data = data

    @property
    def id(self) -> str:
        """ Internal file ID. """
        return self._data["_id"]

    @property
    def name(self) -> str:
        """ File name. """
        return self._data["name"]

    @property
    def type(self) -> str:
        """ File type. """
        return self._data["type"]


class Attachment:
    """
    Attachment object from the realtime API.
    `API reference page`_.

    .. _`API reference page`:
        https://rocket.chat/docs/developer-guides/rest-api/chat/sendmessage/#attachments-detail
    """

    def __init__(self, data: dict):
        self._data = data

    @property
    def title(self) -> str:
        """ Title of the attachment. """
        return self._data["title"]

    @property
    def type(self) -> str:
        """ Attachment type. """
        return self._data["type"]

    @property
    def description(self) -> str:
        """ Attachment description. """
        return self._data["description"]

    @property
    def title_link(self) -> str:
        """ Clickable title. """
        return self._data["title_link"]

    @property
    def title_link_download(self) -> bool:
        """ ``True`` if the title link is down-loadable. """
        return self._data["title_link_download"]

    @property
    def image_url(self) -> str:
        """ URL to the displayed image. """
        return self._data["image_url"]

    @property
    def image_size(self) -> int:
        """ Size of the image. """
        return self._data["image_size"]

    @property
    def image_width(self) -> int:
        """ Image width. """
        return self._data["image_dimensions"]["width"]

    @property
    def image_height(self) -> int:
        """ Image height. """
        return self._data["image_dimensions"]["height"]

    @property
    def image_preview(self) -> str:
        """ Image preview data. """
        return self._data["image_preview"]


class Mention:
    """ Mention object. """

    def __init__(self, data: dict):
        self._data = data

    @property
    def id(self) -> str:
        """ Internal mention ID. """
        return self._data["_id"]

    @property
    def name(self) -> str:
        """ Mention name. """
        return self._data["name"]

    @property
    def username(self) -> str:
        """ Mention username. """
        return self._data["username"]


class Reaction:
    """ Reaction object. """

    def __init__(self, key: str, value: dict):
        self._key = key
        self._value = value

    def reaction(self) -> str:
        """ Emoji reaction. """
        return self._key

    def usernames(self) -> List[str]:
        """ List of users that reacted. """
        return self._value["usernames"]


class Channel:
    """ Channel object. """

    def __init__(self, data: dict):
        self._data = data

    @property
    def id(self) -> str:
        """ Internal channel ID. """
        return self._data["_id"]

    @property
    def name(self) -> str:
        """ Channel name. """
        return self._data["name"]


class Room:
    """
    Chat room object.
    `API reference page`_.

    .. _`API reference page`:
        https://rocket.chat/docs/developer-guides/realtime-api/the-room-object/
    """

    def __init__(self, data: dict):
        self._data = data

    @property
    def paricipant(self) -> bool:
        """ ``True`` if the user is a participant. """
        return self._data["roomParticipant"]

    @property
    def type(self) -> str:
        """
        Room type, one of::

            * ``"d"`` Direct chat
            * ``"c"`` Chat
            * ``"p"`` Private chat
            * ``"l"`` Livechat
        """
        return self._data["roomType"]

    @property
    def name(self) -> str:
        """ Room name. """
        return self._data["roomName"]


class Message:
    """
    Message object from the realtime API.
    `API reference page`_.

    .. _`API reference page`:
        https://rocket.chat/docs/developer-guides/realtime-api/the-message-object/
    """

    def __init__(self, data: List[dict]):
        self._data = data[0]
        self._room_data = data[1]

    @property
    def id(self) -> str:
        """ Message ID. """
        return self._data["_id"]

    @property
    def room_id(self) -> str:
        """ Room that the message belongs to. """
        return self._data["rid"]

    @property
    def text(self) -> str:
        """ Textual message. """
        return self._data["msg"]

    @property
    def timestamp(self) -> int:
        """ Epoch timestamp. """
        return self._data["ts"]["$date"]

    @property
    def user(self) -> User:
        """ User structure. """
        return User(self._data["u"])

    @property
    def user_id(self) -> str:
        """ ID of the user that sent the message. """
        return self._data["u"]["_id"]

    @property
    def username(self) -> str:
        """ Username of the user that sent the message. """
        return self._data["u"]["username"]

    @property
    def updated(self) -> int:
        """ Epoch timestamp of when the message got saved on the server. """
        return self._data["_updatedAt"]["$date"]

    @property
    def edited_at(self) -> Optional[int]:
        """ Epoch timestamp of the last edit.  ``None`` if not edited. """
        try:
            return self._data["editedAt"]["$date"]
        except KeyError:
            return None

    @property
    def edited_by(self) -> Optional[User]:
        """ User that made the edit.  ``None`` if not edited. """
        try:
            return User(self._data["editedBy"])
        except KeyError:
            return None

    @property
    def attachments(self) -> List[Attachment]:
        """ List of attachments on the message. """
        try:
            return [Attachment(d) for d in self._data["attachments"]]
        except KeyError:
            return []

    @property
    def file(self) -> Optional[File]:
        """ File uploaded with the message, if it exists. """
        try:
            return File(self._data["file"])
        except KeyError:
            return None

    @property
    def mentions(self) -> List[Mention]:
        """ Mentions. """
        return [Mention(d) for d in self._data["mentions"]]

    @property
    def reactions(self) -> List[Reaction]:
        """ Reactions. """
        try:
            return [Reaction(k, v) for k, v in self._data["reactions"].items()]
        except KeyError:
            return []

    @property
    def channels(self) -> List[Channel]:
        """ Channels. """
        return [Channel(d) for d in self._data["channels"]]

    @property
    def room(self) -> Room:
        """ Room information. """
        return Room(self._room_data)
