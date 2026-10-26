"""Terminal dashboard: reads the engine's telemetry block and draws the top of the book.

    python -m chronosmatch.dashboard --telemetry PATH          # live, curses (q to quit)
    python -m chronosmatch.dashboard --telemetry PATH --once   # print one frame as plain text

`render_lines` builds the screen as (text, style) lines and is pure, so it is unit-tested
without a terminal; curses only paints those lines.
"""

import argparse
import curses
import sys
import time

from chronosmatch import config
from chronosmatch.telemetry import Snapshot, TelemetryBlock

Line = tuple[str, str]  # (text, style): style is one of normal, header, bid, ask, dim
_BAR_WIDTH = 30


def _progress_bar(done: int, total: int) -> str:
    filled = _BAR_WIDTH * done // total if total else 0
    return "[" + "#" * filled + "." * (_BAR_WIDTH - filled) + "]"


def render_lines(snap: Snapshot | None) -> list[Line]:
    if snap is None:
        return [("ChronosMatch live", "header"), ("waiting for the engine to publish...", "dim")]

    pct = 100 * snap.processed / snap.target_count if snap.target_count else 0.0
    fmt = lambda v: "-" if v is None else str(v)  # noqa: E731
    lines: list[Line] = [
        ("ChronosMatch live  |  firehose -> mmap ring -> Cython engine", "header"),
        (f"orders {snap.processed:,} / {snap.target_count:,} ({pct:.1f}%) "
         f"{_progress_bar(snap.processed, snap.target_count)}", "normal"),
        ("", "normal"),
        (f"BEST BID {fmt(snap.best_bid):>6}   BEST ASK {fmt(snap.best_ask):>6}   "
         f"SPREAD {fmt(snap.spread):>4}", "header"),
        (f"throughput {snap.orders_per_sec:>12,} orders/s    trades {snap.trades:,} "
         f"(qty {snap.traded_qty:,})", "normal"),
        (f"latency entry->match  p50 {snap.latency_p50_ns / 1_000:,.2f} us   "
         f"p99 {snap.latency_p99_ns / 1_000:,.2f} us   "
         f"(last {config.TELEMETRY_LATENCY_SAMPLE:,} orders)", "normal"),
        ("", "normal"),
        (f"{'BIDS':^22}    {'ASKS':^22}", "header"),
        (f"{'price':>10} {'qty':>11}    {'price':>10} {'qty':>11}", "dim"),
    ]
    for i in range(config.TELEMETRY_DEPTH):
        bid = f"{snap.bids[i][0]:>10} {snap.bids[i][1]:>11,}" if i < len(snap.bids) else " " * 22
        ask = f"{snap.asks[i][0]:>10} {snap.asks[i][1]:>11,}" if i < len(snap.asks) else " " * 22
        lines.append((f"{bid}    {ask}", "book"))
    lines.append(("", "normal"))
    lines.append(("status: DONE" if snap.done else "status: RUNNING", "header" if snap.done else "normal"))
    return lines


def _init_styles() -> dict[str, int]:
    styles = {"normal": curses.A_NORMAL, "header": curses.A_BOLD, "dim": curses.A_DIM,
              "bid": curses.A_NORMAL, "ask": curses.A_NORMAL, "book": curses.A_NORMAL}
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_GREEN, -1)
        curses.init_pair(2, curses.COLOR_RED, -1)
        styles["bid"] = curses.color_pair(1)
        styles["ask"] = curses.color_pair(2)
    return styles


def _paint(stdscr, lines: list[Line], styles: dict[str, int], footer: str) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    for y, (text, style) in enumerate(lines[: height - 2]):
        if style == "book":  # bids half green, asks half red
            stdscr.addnstr(y, 0, text[:22], width - 1, styles["bid"])
            if width > 27:
                stdscr.addnstr(y, 26, text[26:], width - 27, styles["ask"])
        else:
            stdscr.addnstr(y, 0, text, width - 1, styles[style])
    if height > 1:
        stdscr.addnstr(height - 1, 0, footer, width - 1, styles["dim"])
    stdscr.refresh()


def run_curses(telemetry: TelemetryBlock, footer: str = "q: quit") -> None:
    """Draw until the user presses q."""

    def loop(stdscr) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        stdscr.nodelay(True)
        styles = _init_styles()
        while stdscr.getch() not in (ord("q"), ord("Q")):
            _paint(stdscr, render_lines(telemetry.read()), styles, footer)
            time.sleep(config.DASHBOARD_REFRESH_S)

    curses.wrapper(loop)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ChronosMatch terminal dashboard.")
    parser.add_argument("--telemetry", required=True)
    parser.add_argument("--once", action="store_true", help="print one frame as text and exit")
    args = parser.parse_args(argv)
    with TelemetryBlock.attach(args.telemetry) as tel:
        if args.once:
            print("\n".join(text for text, _ in render_lines(tel.read())))
        else:
            run_curses(tel)
    return 0


if __name__ == "__main__":
    sys.exit(main())
