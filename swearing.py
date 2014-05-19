import curses

unkey = dict(
    (getattr(curses, k), k[len('KEY_'):])
    for k in dir(curses)
    if k.startswith('KEY_'))

def main():
    stdscr = curses.initscr()
    curses.noecho()
    curses.nonl()
    curses.raw()
    stdscr.keypad(1)
    stdscr.scrollok(1)

    stdscr.addstr('press q to quit\n')

    x = None
    while x != 'q':
        x = stdscr.get_wch()
        stdscr.addstr('%s %s %s %s\n' % (
            type(x),
            repr(x),
            repr(x) if isinstance(x, str) else curses.keyname(x),
            repr(x) if isinstance(x, str) else unkey[x],
            ))

    curses.noraw()
    curses.nl()
    curses.echo()
    curses.endwin()

if __name__ == '__main__':
    main()
