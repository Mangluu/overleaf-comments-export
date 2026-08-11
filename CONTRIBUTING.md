# Contributing

Contributions are welcome, including from people who have never contributed to
an open source project before. Bug reports and "this was confusing" notes are
as useful as code.

## The most useful thing you can do

Tell me when it breaks. This tool talks to Overleaf's internal endpoints, which
can change without warning. If it suddenly stops working for you, please
[open an issue](https://github.com/Mangluu/overleaf-comments-export/issues/new/choose)
— you may be the first person to notice, and nothing gets fixed if everyone
assumes someone else reported it.

Never include your session cookie in an issue. It is a password for your
Overleaf account and nobody needs it to fix a bug.

## Running it from source

```bash
git clone https://github.com/Mangluu/overleaf-comments-export.git
cd overleaf-comments-export
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[gui,test]"
pytest                      # 70 tests, ~0.1s, no network needed
overleaf-comments-export --gui
```

The tests are all offline. If a change you make needs the network to be tested,
that is usually a sign it should be split so the logic can be tested without it.

## How the code fits together

Seven small modules, each with one job:

| File | Does |
|---|---|
| `client.py` | Talks to Overleaf: auth (browser cookie or pasted), HTTP with retries, friendly errors. Every network call goes through `_request`. |
| `export.py` | The orchestration. Fetches, resolves anchors, applies filters, writes every output file. |
| `anchors.py` | Turns a character offset into a line and column, and relocates anchors whose text has moved. |
| `sections.py` | Finds LaTeX headings so each comment knows which section it belongs to. |
| `render.py` | Markdown output, compact and detailed. |
| `model.py` | Dataclasses. No logic. |
| `gui.py` | The Tkinter window. Runs the export on a worker thread. |

Two things worth knowing before you change anything:

- **An Overleaf thread is flat.** A "reply" is just a later message in the same
  thread — there is no nesting, and no parent pointer. The first message by
  timestamp is the comment; everything after it is a reply.
- **Anchors go stale.** Comments are stored as a character offset plus the text
  they were attached to. If the document changed, the offset lies. That is what
  `resolve_anchor` is for, and why exports carry a `stale` flag.

## Style

Match the surrounding code. Keep the diff small. A comment explaining *why*
beats a comment explaining *what*.

New behaviour needs a test. Not a suite — one test that fails if the behaviour
breaks. Look at `tests/test_replies_and_changes.py` for the shape.

## Pull requests

Open an issue first for anything large, so you do not spend a weekend on
something I would turn down. Small fixes can go straight to a PR.

CI runs the tests on Linux, macOS, and Windows across Python 3.10 to 3.13. It
must be green before merge.

## A note on scope

This tool reads. It does not write back to Overleaf — no posting replies, no
marking threads resolved. That boundary is deliberate: it keeps the tool safe
to run and keeps it clearly within what your own account can already see.
Please do not send a PR that crosses it.
