# Stubs for wsproto.utilities (Python 3)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from typing import Any, Optional

ACCEPT_GUID: bytes

class ProtocolError(Exception): ...
class LocalProtocolError(ProtocolError): ...

class RemoteProtocolError(ProtocolError):
    event_hint: Any = ...
    def __init__(self, message: str, event_hint: Any=...) -> None: ...

def normed_header_dict(h11_headers: Any): ...
def split_comma_header(value: Any): ...
def generate_nonce(): ...
def generate_accept_token(token: Any): ...