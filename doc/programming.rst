Programming snipe
=================

snipe module
============

Central Infrastructure
----------------------

.. automodule:: snipe.main

.. automodule:: snipe.context

.. automodule:: snipe.interactive

.. automodule:: snipe.util

nonspecific UI
--------------

.. automodule:: snipe.keymap

.. automodule:: snipe.ttycolor

.. automodule:: snipe.ttyfe

.. automodule:: snipe.window

"modes"
-------

.. automodule:: snipe.editor

.. automodule:: snipe.messager

.. automodule:: snipe.help

talking to message services
----------------------------
.. automodule:: snipe.messages

.. py:module:: snipe.filters


^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
external interface of the filter mechanism
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. autofunction:: snipe.filters.makefilter
.. autofunction:: snipe.filters.validatefilter
.. autoexception:: snipe.filters.SnipeFilterError

^^^^^^^^^^^^
filter parts
^^^^^^^^^^^^

.. autoclass:: snipe.filters.Yes
.. autoclass:: snipe.filters.No
.. autoclass:: snipe.filters.And
.. autoclass:: snipe.filters.Not
.. autoclass:: snipe.filters.Or
.. autoclass:: snipe.filters.Compare
.. autoclass:: snipe.filters.FilterLookup
.. autoclass:: snipe.filters.Python
.. autoclass:: snipe.filters.RECompare
.. autoclass:: snipe.filters.Xor

^^^^^^^^^^^
filter guts
^^^^^^^^^^^

.. autoclass:: snipe.filters.Filter
.. autoclass:: snipe.filters.Certitude
.. autoclass:: snipe.filters.Comparison
.. autoclass:: snipe.filters.Conjunction
.. autoclass:: snipe.filters.Truth

^^^^^^^^^^^
Parser guts
^^^^^^^^^^^

.. autoclass:: snipe.filters.Regexp
.. autoclass:: snipe.filters.Identifier
.. autoclass:: snipe.filters.Lexeme
.. autoclass:: snipe.filters.Lexer
   :no-members:
.. autoclass:: snipe.filters.Parser
   :no-members:
.. autoclass:: snipe.filters.PlyShim

.. automodule:: snipe.irccloud

.. automodule:: snipe.roost

behind the backends
-------------------

.. automodule:: snipe._rooster

.. automodule:: snipe._websocket

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
