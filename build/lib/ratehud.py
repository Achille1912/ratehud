"""
Claude Code live usage monitor.

Run:
    python claude_usage_monitor.py [--theme dracula|nord|matrix|mono]

Shows how close you are to your plan's 5h/7d usage limits, meant to live in
a terminal split.
"""

import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.progress_bar import ProgressBar
from rich.box import Box

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"

THEMES = {
    "dracula": {"primary": "#bd93f9", "accent": "#50fa7b", "warn": "#ffb86c", "dim": "#6272a4"},
    "nord": {"primary": "#88c0d0", "accent": "#a3be8c", "warn": "#ebcb8b", "dim": "#4c566a"},
    "matrix": {"primary": "#00ff9f", "accent": "#00ff9f", "warn": "#ffffff", "dim": "#008855"},
    "mono": {"primary": "#ffffff", "accent": "#dddddd", "warn": "#999999", "dim": "#666666"},
}

# A ROUNDED box with its straight edges swapped for dashed glyphs. Swapping which
# dash glyph is used (dashed_box(0) vs dashed_box(1)) between renders is what makes
# the border look like it's crawling, since Live keeps repainting on its own clock.
_ROUNDED_TEMPLATE = "╭─┬╮\n│ ││\n├─┼┤\n│ ││\n├─┼┤\n├─┼┤\n│ ││\n╰─┴╯\n"


def dashed_box(phase: int) -> Box:
    horizontal, vertical = ("╌", "┆") if phase % 2 == 0 else ("┄", "╎")
    return Box(_ROUNDED_TEMPLATE.replace("─", horizontal).replace("│", vertical))


class RateLimits:
    """Plan usage limits (5h session + 7d weekly), read from live API response headers.

    The percentages aren't stored anywhere on disk - Claude Code receives them as HTTP
    headers on every request and never persists them. So the only way to show them is
    to make our own minimal authenticated request and read the headers back.
    """

    def __init__(self):
        self.status: str | None = None
        self.five_hour: float | None = None
        self.five_hour_status: str | None = None
        self.five_hour_reset: int | None = None
        self.seven_day: float | None = None
        self.seven_day_status: str | None = None
        self.seven_day_reset: int | None = None
        self.binding: str | None = None  # which bucket actually constrains you right now
        self.overage_status: str | None = None
        self.overage_disabled_reason: str | None = None
        self.checked_at: float | None = None
        self.error: str | None = None


def load_oauth_token() -> str | None:
    try:
        data = json.loads(CREDENTIALS_PATH.read_text(encoding="utf-8"))
        return data["claudeAiOauth"]["accessToken"]
    except (OSError, KeyError, json.JSONDecodeError):
        return None


def fetch_rate_limits(state: RateLimits) -> None:
    token = load_oauth_token()
    if not token:
        state.error = "no Claude subscription credentials found"
        return

    # The cheapest possible request: 1 output token is enough to get the rate-limit
    # headers back; the content of the call itself is irrelevant.
    body = json.dumps({
        "model": "claude-haiku-4-5",
        "max_tokens": 1,
        "messages": [{"role": "user", "content": "hi"}],
    }).encode()
    request = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            headers = response.headers
    except urllib.error.HTTPError as error:
        headers = error.headers  # Anthropic returns rate-limit headers on errors too.
        if error.code == 401:
            state.error = "token expired - run `claude` once to refresh it"
            return
    except (urllib.error.URLError, TimeoutError) as error:
        state.error = f"network error: {error}"
        return

    def read_float(name: str) -> float | None:
        value = headers.get(name)
        return float(value) if value is not None else None

    def read_int(name: str) -> int | None:
        value = headers.get(name)
        return int(value) if value is not None else None

    state.status = headers.get("anthropic-ratelimit-unified-status")
    state.five_hour = read_float("anthropic-ratelimit-unified-5h-utilization")
    state.five_hour_status = headers.get("anthropic-ratelimit-unified-5h-status")
    state.five_hour_reset = read_int("anthropic-ratelimit-unified-5h-reset")
    state.seven_day = read_float("anthropic-ratelimit-unified-7d-utilization")
    state.seven_day_status = headers.get("anthropic-ratelimit-unified-7d-status")
    state.seven_day_reset = read_int("anthropic-ratelimit-unified-7d-reset")
    state.binding = headers.get("anthropic-ratelimit-unified-representative-claim")
    state.overage_status = headers.get("anthropic-ratelimit-unified-overage-status")
    state.overage_disabled_reason = headers.get("anthropic-ratelimit-unified-overage-disabled-reason")
    state.checked_at = time.time()
    state.error = None


def format_time_left(reset_ts: int | None) -> str:
    if reset_ts is None:
        return "?"
    seconds = max(0, reset_ts - int(time.time()))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    return f"{hours}h{minutes:02d}m"


def render_limits(rl: RateLimits, theme: dict) -> Panel:
    colors = theme
    body = Table.grid(padding=(0, 0))
    body.add_column(width=36)
    phase = int(time.time() * 2)  # flips twice a second, driven purely by the wall clock

    if rl.error:
        body.add_row(Text(rl.error, style=colors["dim"]))
        return Panel(body, title="[bold]plan limits[/bold]", border_style=colors["dim"], box=dashed_box(phase), width=38)

    overall_ok = rl.status == "allowed"
    overall_dot = colors["accent"] if overall_ok else colors["warn"]
    header = Table.grid(expand=True)
    header.add_column(ratio=1)
    header.add_column(justify="right")
    checked = int(time.time() - rl.checked_at) if rl.checked_at else None
    header.add_row(
        Text(f"● {rl.status or 'unknown'}", style="bold " + overall_dot),
        Text(f"checked {checked}s ago" if checked is not None else "", style=colors["dim"]),
    )
    body.add_row(header)
    body.add_row(Text(""))

    for key, label, pct, status, reset in (
        ("five_hour", "5h session", rl.five_hour, rl.five_hour_status, rl.five_hour_reset),
        ("seven_day", "7d weekly", rl.seven_day, rl.seven_day_status, rl.seven_day_reset),
    ):
        pct = pct or 0.0
        bar_color = colors["warn"] if pct >= 0.9 else colors["accent"]
        tag = "" if status in (None, "allowed") else f" [{colors['warn']}]{status}[/]"
        bind_mark = "  ←" if rl.binding == key else ""

        pct_line = Table.grid(expand=True)
        pct_line.add_column(ratio=1)
        pct_line.add_column(justify="right")
        pct_line.add_row(Text(f"{pct:.0%} used", style="bold " + colors["primary"]), Text.from_markup(tag))
        body.add_row(pct_line)

        body.add_row(ProgressBar(
            total=1.0, completed=pct, width=30,
            complete_style=bar_color, finished_style=bar_color,
        ))

        row = Table.grid(expand=True)
        row.add_column(ratio=1)
        row.add_column(justify="right")
        row.add_row(
            Text(f"{label}{bind_mark}", style=colors["dim"]),
            Text(f"resets in {format_time_left(reset)}", style=colors["dim"]),
        )
        body.add_row(row)
        body.add_row(Text(""))

    if rl.binding:
        body.add_row(Text(f"binding limit: {rl.binding.replace('_', ' ')}", style=colors["dim"]))

    if rl.overage_status and rl.overage_status != "rejected":
        body.add_row(Text(f"overage: {rl.overage_status}", style=colors["dim"]))
    elif rl.overage_disabled_reason:
        short_reason = "org" if "org" in rl.overage_disabled_reason else rl.overage_disabled_reason.split("_")[0]
        body.add_row(Text(f"overage: off ({short_reason})", style=colors["dim"]))

    return Panel(
        body,
        title="[bold]plan limits[/bold]",
        border_style=overall_dot,
        box=dashed_box(phase),
        width=38,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--theme", choices=THEMES.keys(), default="dracula")
    parser.add_argument(
        "--limit-interval", type=float, default=60.0,
        help="seconds between checks of the 5h/7d plan limits (each check is one tiny live API call)",
    )
    args = parser.parse_args()

    theme = THEMES[args.theme]
    console = Console()

    rate_limits = RateLimits()
    fetch_rate_limits(rate_limits)
    last_limit_check = time.time()

    with Live(render_limits(rate_limits, theme), console=console, refresh_per_second=4, screen=False) as live:
        while True:
            # The border's dash phase is derived from the wall clock, so we need to
            # re-render a few times a second for it to visibly move - not just once
            # a second like the data underneath it actually changes.
            time.sleep(0.25)

            if time.time() - last_limit_check >= args.limit_interval:
                fetch_rate_limits(rate_limits)  # blocking network call, throttled to once a minute
                last_limit_check = time.time()

            live.update(render_limits(rate_limits, theme))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
