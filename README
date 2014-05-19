snipe is (will be?) an "instant" messaging client intended for
services with persistence.  One such service (and the only one snipe
supports at the moment) is roost <https://github.com/roost-im>, which
is a frontend for zephyr <https://github.com/zephyr-im>.

At the moment, to get it working, you need python 3.4 (3.3+asyncio
_might_ be sufficient but I have not tested it) and the aiohttp
library <https://github.com/KeepSafe/aiohttp>; there is a for of
aiohttp with minimal debian packaging at my github
<https://github.com/kcr/aiohttp>.

At the moment, you need to set the environment variable ROOST_API to a
roost server that you already have subs on; import-subs in the
roost-python repo <https://github.com/roost-im/roost-python> is useful
for this.

It is known that there are bugs and missing features everywhere.  
If it breaks you get to keep both pieces.

(Currently, also, the debug log goes to /tmp/snipe.log, which is
world-readable-by default, and is probably a terribly security leak)
