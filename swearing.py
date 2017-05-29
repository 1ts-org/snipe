#!/usr/bin/python3
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

    maxy, maxx = stdscr.getmaxyx()

    stdscr.attrset(curses.A_REVERSE)
    stdscr.addstr('‡\n')
    stdscr.attrset(0)
    x = stdscr.inch(0, 0)
    stdscr.move(2, 0)
    stdscr.addstr(
        'inch(0,0) = %s; A_UNDERLINE=%d\n' % (repr(x), curses.A_UNDERLINE))

    stdscr.addstr(
        'COLORS=%d COLOR_PAIRS=%d has_colors()=%s can_change_color()=%s\n' % (
            curses.COLORS,
            curses.COLOR_PAIRS,
            colors,
            curses.can_change_color()))
    stdscr.addstr('%d\n' % (maxx,))
    rgbs = []
    if colors:
        for i in range(curses.COLORS):
            rgb = '%02x%02x%02x' % tuple(
                int((j / 1000) * 255.0) for j in curses.color_content(i))
            rgbs.append(rgb)
            stdscr.addstr(' %s' % (rgb,))
            if (stdscr.getyx()[1] + 7) > maxx:
                stdscr.addstr('\n')
    stdscr.addstr('\n')
    stdscr.addstr('press a key')
    stdscr.get_wch()
    stdscr.addstr('\n')

    if colors:
        for i in range(min(curses.COLORS, curses.COLOR_PAIRS - 1)):
            curses.init_pair(i+1, -1, i)

    for i in range(1, curses.COLOR_PAIRS):
        stdscr.addstr(' %s' % (rgbs[i-1],), curses.color_pair(i))
        y, x = stdscr.getyx()
        if x + 7 > maxx:
            stdscr.addstr('\n')
    else:
        stdscr.addstr('\n')

    stdscr.addstr('press a key')
    stdscr.get_wch()
    stdscr.addstr('\n')
    if colors:
        if curses.can_change_color():
            for i in range(curses.COLORS):
                curses.init_color(i, 0, 1000, 0)

    stdscr.addstr('press q to quit\n')

    x = None
    while x != 'q':
        x = stdscr.get_wch()
        stdscr.addstr('%s %s %s %s\n' % (
            type(x),
            repr(x),
            repr(x) if isinstance(x, str) else curses.keyname(x),
            repr(x) if isinstance(x, str) else unkey.get(x, '???'),
            ))
        if x == curses.KEY_RESIZE:
            maxy, maxx = stdscr.getmaxyx()
            stdscr.addstr('Resize! %d %d\n' % (maxy, maxx))

    curses.noraw()
    curses.nl()
    curses.echo()
    curses.endwin()


if __name__ == '__main__':
    main()
