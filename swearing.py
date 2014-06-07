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
    colors = curses.has_colors()
    curses.start_color()
    if colors:
        curses.use_default_colors()
    stdscr.keypad(1)
    stdscr.scrollok(1)

    stdscr.addstr(
        'COLORS=%d COLOR_PAIRS=%d has_colors()=%s can_change_color()=%s\n' % (
            curses.COLORS, curses.COLOR_PAIRS, colors, curses.can_change_color()))

    maxy, maxx = stdscr.getmaxyx()

    if colors:
        curses.init_pair(5, curses.COLOR_GREEN, -1)

    for i in range(curses.COLOR_PAIRS):
        stdscr.addstr(' %03d' % (i,), curses.color_pair(i))
        y, x = stdscr.getyx()
        if x + 4 > maxx:
            stdscr.addstr('\n')
    else:
        stdscr.addstr('\n')

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
