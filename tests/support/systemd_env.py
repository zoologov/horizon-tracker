"""Reads an EnvironmentFile the way systemd does, so a test can see the values a unit gets.

A port of ``parse_env_file_internal`` from systemd v255 ``src/basic/env-file.c`` (the
parser ``EnvironmentFile=`` uses through ``load_env_file``): no variable expansion,
single quotes literal, and inside double quotes a backslash unescapes only the four
characters of ``SHELL_NEED_ESCAPE``. The deploy writes ``.env`` for this parser, not
for a shell, so the tests read it back with this parser and not with ``source``.
"""

from enum import Enum, auto

WHITESPACE = " \t\n\r"
NEWLINE = "\n\r"
COMMENTS = "#;"
SHELL_NEED_ESCAPE = '"\\`$'


class _State(Enum):
    PRE_KEY = auto()
    KEY = auto()
    PRE_VALUE = auto()
    VALUE = auto()
    VALUE_ESCAPE = auto()
    SINGLE_QUOTE_VALUE = auto()
    DOUBLE_QUOTE_VALUE = auto()
    DOUBLE_QUOTE_VALUE_ESCAPE = auto()
    COMMENT = auto()
    COMMENT_ESCAPE = auto()


class _Parser:
    """One pass of the systemd state machine over a file's text."""

    def __init__(self) -> None:
        self.state = _State.PRE_KEY
        self.key: list[str] = []
        self.value: list[str] = []
        self.key_ws: int | None = None
        self.value_ws: int | None = None
        self.pairs: dict[str, str] = {}

    def push(self, *, chomp_value: bool) -> None:
        key = self.key if self.key_ws is None else self.key[: self.key_ws]
        value = self.value
        if chomp_value and self.value_ws is not None:
            value = value[: self.value_ws]
        self.pairs["".join(key)] = "".join(value)
        self.key, self.value = [], []

    def feed(self, c: str) -> None:
        """Advance one character; one branch per state, in the order of env-file.c."""
        s = self.state
        if s is _State.PRE_KEY:
            if c in COMMENTS:
                self.state = _State.COMMENT
            elif c not in WHITESPACE:
                self.state, self.key_ws = _State.KEY, None
                self.key.append(c)
        elif s is _State.KEY:
            if c in NEWLINE:
                self.state, self.key = _State.PRE_KEY, []
            elif c == "=":
                self.state, self.value_ws = _State.PRE_VALUE, None
            else:
                if c not in WHITESPACE:
                    self.key_ws = None
                elif self.key_ws is None:
                    self.key_ws = len(self.key)
                self.key.append(c)
        elif s is _State.PRE_VALUE:
            if c in NEWLINE:
                self.state = _State.PRE_KEY
                self.push(chomp_value=False)
            elif c == "'":
                self.state = _State.SINGLE_QUOTE_VALUE
            elif c == '"':
                self.state = _State.DOUBLE_QUOTE_VALUE
            elif c == "\\":
                self.state = _State.VALUE_ESCAPE
            elif c not in WHITESPACE:
                self.state = _State.VALUE
                self.value.append(c)
        elif s is _State.VALUE:
            if c in NEWLINE:
                self.state = _State.PRE_KEY
                self.push(chomp_value=True)
            elif c == "\\":
                self.state, self.value_ws = _State.VALUE_ESCAPE, None
            else:
                if c not in WHITESPACE:
                    self.value_ws = None
                elif self.value_ws is None:
                    self.value_ws = len(self.value)
                self.value.append(c)
        elif s is _State.VALUE_ESCAPE:
            self.state = _State.VALUE
            if c not in NEWLINE:
                self.value.append(c)
        elif s is _State.SINGLE_QUOTE_VALUE:
            if c == "'":
                self.state = _State.PRE_VALUE
            else:
                self.value.append(c)
        elif s is _State.DOUBLE_QUOTE_VALUE:
            if c == '"':
                self.state = _State.PRE_VALUE
            elif c == "\\":
                self.state = _State.DOUBLE_QUOTE_VALUE_ESCAPE
            else:
                self.value.append(c)
        elif s is _State.DOUBLE_QUOTE_VALUE_ESCAPE:
            self.state = _State.DOUBLE_QUOTE_VALUE
            if c in SHELL_NEED_ESCAPE:
                self.value.append(c)
            elif c != "\n":
                self.value.extend(("\\", c))
        elif s is _State.COMMENT:
            if c == "\\":
                self.state = _State.COMMENT_ESCAPE
            elif c in NEWLINE:
                self.state = _State.PRE_KEY
        elif s is _State.COMMENT_ESCAPE:
            self.state = _State.PRE_KEY if c in NEWLINE else _State.COMMENT

    def finish(self) -> dict[str, str]:
        if self.state not in (_State.PRE_KEY, _State.KEY, _State.COMMENT, _State.COMMENT_ESCAPE):
            self.push(chomp_value=self.state is _State.VALUE)
        return self.pairs


def parse_env_file(text: str) -> dict[str, str]:
    """The variables a unit with ``EnvironmentFile=`` pointing at ``text`` would receive."""
    parser = _Parser()
    for c in text:
        parser.feed(c)
    return parser.finish()
