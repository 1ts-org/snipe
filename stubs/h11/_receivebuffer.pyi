# Stubs for h11._receivebuffer (Python 3)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from typing import Any

class ReceiveBuffer:
    def __init__(self) -> None: ...
    def __bool__(self): ...
    def __bytes__(self): ...
    __nonzero__: Any = ...
    def __len__(self): ...
    def compress(self) -> None: ...
    def __iadd__(self, byteslike: Any): ...
    def maybe_extract_at_most(self, count: Any): ...
    def maybe_extract_until_next(self, needle: Any): ...
    def maybe_extract_lines(self): ...
