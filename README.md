# ratehud

A small terminal tool that shows how close you are to your Claude subscription's
usage limits (the 5 hour session limit and the 7 day weekly limit), live, in a
panel meant to sit in a terminal split while you work with Claude Code.

It is cross platform (Linux, macOS, Windows) and only has one dependency: `rich`.

## What it shows

- Overall status (allowed or rejected)
- 5h session usage, as a percentage, with a progress bar and the time until it resets
- 7d weekly usage, same format
- Which of the two limits is currently the binding one (the one that will stop you first)
- Whether overage billing is enabled or disabled for your account, and why

## How it works

Claude Code receives your plan's usage percentages as HTTP response headers on
every API request it makes, but it never writes them to disk. There is no local
file to read them from.

This tool works around that by reading the OAuth access token already saved by
Claude Code at `~/.claude/.credentials.json`, and making a minimal API request of
its own (1 output token, effectively free) just to read the rate limit headers
back from the response. It does this once at startup and then on a timer
(every 60 seconds by default).

The token is read from disk by the script itself and is never printed, logged,
or sent anywhere other than `api.anthropic.com`.

## Requirements

- Python 3.10 or newer
- A Claude Code login (the tool reads the same credentials file Claude Code uses)
- The `rich` package

## Installation

### Linux / macOS

```
git clone <this-repo-url>
cd ratehud
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Windows (PowerShell)

```
git clone <this-repo-url>
cd ratehud
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Usage

Run it with the virtual environment's Python directly:

```
.venv/bin/python ratehud.py
```

On Windows:

```
.venv\Scripts\python ratehud.py
```

Or activate the virtual environment once per terminal session and use `python`
normally afterward:

```
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows

python ratehud.py
```

Leave it running in a split pane. It redraws itself in place, it does not
scroll your terminal. Stop it with Ctrl+C.

### Options

| Flag | Default | Description |
|---|---|---|
| `--theme` | `dracula` | Color theme. One of `dracula`, `nord`, `matrix`, `mono`. |
| `--limit-interval` | `60` | Seconds between checks of the usage limits. Each check is one small live API call. |

Example:

```
.venv/bin/python ratehud.py --theme matrix --limit-interval 120
```

## Notes and limitations

- This tool makes a real, small API call on a timer using your own credentials.
  It is not free in the strictest sense: it consumes a tiny, generally
  negligible amount of your 5h/7d quota every time it checks.
- If your OAuth token has expired, the panel will tell you to run `claude` once
  to refresh it, rather than crashing.
- If no Claude Code credentials file is found, the panel shows an error instead
  of usage data.
- The usage limit header names used here are not part of Anthropic's public,
  documented API. They were discovered by inspecting real response headers and
  could change without notice.

## License

MIT
