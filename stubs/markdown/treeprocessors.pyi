# Stubs for markdown.treeprocessors (Python 3)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from . import util
from typing import Any

def build_treeprocessors(md_instance: Any, **kwargs: Any): ...
def isString(s: Any): ...

class Treeprocessor(util.Processor):
    def run(self, root: Any) -> None: ...

class InlineProcessor(Treeprocessor):
    markdown: Any = ...
    inlinePatterns: Any = ...
    def __init__(self, md: Any) -> None: ...
    stashed_nodes: Any = ...
    def run(self, tree: Any): ...

class PrettifyTreeprocessor(Treeprocessor):
    def run(self, root: Any) -> None: ...
