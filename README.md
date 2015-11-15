snipe is a text-oriented (currently curses-based) "instant" messaging
client intended for services with persistence.  One such service is
[roost](https://github.com/roost-im), which is a frontend for
[zephyr](https://github.com/zephyr-im).  snipe is also has
minimal support for [IRCCloud](https://www.irccloud.com).

At the moment, to get it working, you need python 3.4. (3.3 _might_ be
sufficient but I have not tested it) and the
[aiohttp](https://github.com/KeepSafe/aiohttp) library; there is a
[fork](https://github.com/kcr/aiohttp) of aiohttp with minimal debian
packaging at my github.

M-g in the messager window requires
[parsedatetime](https://github.com/bear/parsedatetime).

It points itself at roost-api.mit.edu by default.  If you want to
override that, you can use the roost.url config key.  At the moment,
you need to set up subscriptions by some other means; import-subs in
the [roost-python](https://github.com/roost-im/roost-python) repo is
useful for this.

It is known that there are bugs and missing features everywhere.  I
would mostly characterize this as "demoable" but not yet "usable".  As
always, if it breaks you get to keep both pieces.

Keybindings
-----------

(the Meta (Alt?) prefix can always be typed as Escape)

### All Windows

key      | binding
---------|----------------
^X ^C | Quit
^Z    | Suspend
^X 2  | Split current window
^X 0  | delete current window
^X 1  | delete other windows
^X o  | switch windows
^X e  | pop up an empty editor window
^X 4 m | split to a messager window
^X 4 / | split to a messager window with a specified filter
^X c  | test colors
Meta–Escape | evaluate python expressions
Meta–=      | set configuration keys  (^U Alt-= shows you the current configuration)
Meta–[number], ^U | emacs-like arguments
^L | force a reframe

### Most Windows

key  | binding
-----|----------
^V, ⇟ | Page Down
Meta–v, ⇞ | Page Up


### "Messager" windows

key      | binding
---------|----------------
p, ↑     | previous message
n, ↓     | next message
{, Meta–p    | previous message like this one
}, Meta–n    | previous message like this one
[        | previous "stark" point(best guess as when you scrolled to the bottom and stopped reading)
]        | next "stark" point
.        | set a "stark" point
s        | send a message (see Sending, below)
f        | followup (publicly, if applicable) to the current message
r        | reply (privately) to the current message
Meta–<, ↖, Shift-↖ | First (currently loaded)
Meta–>, ↘, Shift-↘ | Last message
^X [     | previous day
^X ]     | next day
^Space, ^@ | set mark
^X ^X | exchange point and mark
Meta-g | goto an absolute time in the message window
/ 0, Meta–/ 0 | Reset the filter to the default
/ =, Meta–/ = | Edit the current filter
/ -, Meta–- | Filter everything
/ g, Meta–/ g | set a foreground/background color rule for the current filter (and reset)
/ f, Meta–/ f | set a foreground color rule for the current filter (and reset)
/ b, Meta–/ b | set a background color rule for the current filter (and reset)
/ c, Meta–/ c | push an approximate match filter on a specified class
/ p, Meta–/ p | push a filter on personal messages
/ s, Meta–/ s | push a filter on specified sender
/ /, Meta–/ / | push a filter based on the current message.  More ^Us increase specificity, if the backend supports it
/ w, Meta–/ Meta–/ | pop the filter stack
/ S, Meta–/ S | Save the current filter (with a prefix, save as the default)
Meta–i | popup a window with gunk about the current message
R S | dump zephyr (roost) subscriptions into a window
R s | subscribe to a zephyr class
R u | unsubscribe from a zephyr class

### "Editor" windows

Basically emacs, for now

key      | binding
---------|----------------
^F, → | forward character
^B, ← | backward character
^N, ↓ | next line
^P, ↑ | previous line
^A, ↖ | beginning of line
^E, ↘ | end of line
Meta–<, Shift-↖ | Beginning of buffer
Meta–>, Shift-↘ | End of buffer
Meta–f | forward word
Meta–b | backward word
Meta–w | copy region
^Space, ^@ | set mark
^X ^X | exchange point and mark
^D, ⌦ | delete character forward
^H, ^?, ⌫ | delete character barckward
^X f | set fill column
^K | kill to end of line
^W | kill region
^Y | yank
Meta-y | yank-pop
^_, ^X u | undo
^T | transpose characters
^O | open line
Meta-^H, Meta-⌫ | kill word backwards
Meta-d | kill word forwards
^X i | insert file
^X ^Q | toggle readonly

### "Sender"/"Prompt" windows are like "Editor" windows except
key      | binding
---------|----------------
^J, ^C ^C | send message, complete operation
^X 0, ^G | delete current window & abort operation
Meta-p | previous history
Meta-n | next history
[tab] | where appropriate, complete

### Replies, specifically
key      | binding
---------|----------------
^C ^Y | yank replied-to-message with '> ' prefix

Sending
-------

The "general" form of an address for sending is `backendname;
address`, where address is a ascii blob entirely determined by the
backend.  For the `roost` backend, it looks (and behaves) a lot like the arguments
to zwrite; e.g. `roost; -c kcr -i snipe` or `roost;kcr`.  You can
abbreviate the backend name to the shortest unique prefix, which in
the case of `roost` and `irccloud` are, conveniently, `r` and `i`
respectively.

For the `irccloud` backend, addresses are of the form `irccloud; server.domain.name recipient`,
e.g. `irccloud; irc.debian.org kcr`.  You can use unique substrings of the server name; e.g.
`i;debian #debian-devel`.
