"""Text a target wrote, made safe to print in a terminal."""


def printable(line: str) -> str:
    """Escape every control character in one report line, newlines included.

    Evidence, titles and references are text the target wrote: an escape sequence in
    them can clear or repaint the warning above it, and a newline can forge a line of
    the report. The only line breaks printed are the ones `render` joins with.
    """
    if line.isprintable():
        return line
    return "".join(_CONTROL_ESCAPES.get(c, c) for c in line)


_CONTROL_ESCAPES = {
    chr(code): {"\t": "\\t", "\n": "\\n", "\r": "\\r"}.get(chr(code), f"\\x{code:02x}")
    for code in (*range(0x20), *range(0x7F, 0xA0))
}
