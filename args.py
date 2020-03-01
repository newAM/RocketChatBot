import argparse
import dataclasses
import queue
from typing import Optional
from typing import Type


@dataclasses.dataclass
class arg:  # noqa: N801
    name: str
    type: Optional[Type] = None
    help: Optional[str] = None


class ArgumentParser(argparse.ArgumentParser):

    msg_q = queue.Queue()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _print_message(self, message, file=None):
        if message:
            self.msg_q.put_nowait(message)

    def exit(self, status=0, message=None):
        pass

    def error(self, message: str):
        raise Exception(message)
