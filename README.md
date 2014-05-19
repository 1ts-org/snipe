snipe is (will be?) a text-oriented (currently curses-based) "instant"
messaging client intended for services with persistence.  One such
service (and the only one snipe supports at the moment) is
[roost](https://github.com/roost-im), which is a frontend for
[zephyr](https://github.com/zephyr-im).

At the moment, to get it working, you need python 3.4 (3.3+asyncio
_might_ be sufficient but I have not tested it) and the
[aiohttp](https://github.com/KeepSafe/aiohttp) library; there is a
[fork](https://github.com/kcr/aiohttp) of aiohttp with minimal debian
packaging at my github.

At the moment, you need to set the environment variable ROOST_API to a
roost server that you already have subs on; import-subs in the
[roost-python](https://github.com/roost-im/roost-python) repo is useful
for this.

It is known that there are bugs and missing features everywhere.  I
would characterize this as "demoable" but not yet "usable".  If it
breaks you get to keep both pieces.

(Currently, also, the debug log goes to /tmp/snipe.log, which is
world-readable-by default, and is probably a terribly security leak)

Keybindings
-----------

### All Windows

key      | binding
---------|----------------
^X ^C | Quit
^Z    | Suspend
^X 2  | Split current dinow
^X 0  | delete current window
^X 1  | delete top popup*
^X o  | switch windows
^X e  | pop up an empty editor window
^X t  | test the "read a string with prompt" popup

### "Messager" windows

key      | binding
---------|----------------
p, ↑     | previous message
n, ↓     | next message
s        | send a message
f        | followup (publicly, if applicable) to the current message
r        | reply (privately) to the current message

### "Editor" windows
key      | binding
---------|----------------
^F, → | forward character
^B, ← | backward character
^N, ↓ | next line
^P, ↑ | previous line
^A, ⇱ | beginning of line
^E, ⇲ | end of line
^T | insert test text
^D, ⌦ | delete character forward
^H, ^?, ⌫ | delete character barckward

### "Sender" windows are like "Editor" windows except
key      | binding
---------|----------------
^J, ^C ^C | send message
