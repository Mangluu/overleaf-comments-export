# The macOS app

`Overleaf Comments Export.app` is a small launcher bundle around the checkout
it is built from. It carries no Python of its own: it finds the virtualenv in
that checkout, checks the packages import, reinstalls them if they do not, and
then starts the window.

## Building it

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[gui,pdf]"
bash packaging/make_app.sh
```

That writes `~/Applications/Overleaf Comments Export.app`, pointed at the
checkout the script lives in. Both arguments are optional:

```bash
bash packaging/make_app.sh /some/folder /path/to/another/checkout
```

## The icon

Six designs live in `icons/`, as SVG and as 1024px PNG, with
`_options-sheet.png` showing them side by side at full size and at the sizes
they are actually seen. `make_icons.py` regenerates all of them.

The one in use is `2-highlight`, a page with a highlighted line, which is what
the commented PDF looks like. It was picked because the yellow is the only
colour in the set that is not green, so it stays recognisable in a Dock full
of document icons, and the highlight survives down to 16 pixels.

```bash
.venv/bin/python packaging/make_icns.py 2-highlight   # or any other name
```

Each size is rendered from the vector rather than downscaled from one large
PNG, so the small ones stay sharp. `make_app.sh` builds the `.icns` on its own
if it is missing, so a fresh clone gives a complete app rather than a blank
one.

## Notes worth keeping

The launcher works out the machine's architecture from `hw.optional.arm64`
rather than `uname -m`. `uname` reports the architecture of the calling
process, so inside a translated one it says x86_64 on an Apple silicon Mac,
and the app then tries to run an arm64 virtualenv under Rosetta and fails to
load every compiled module.

Keep the checkout out of iCloud Drive, Dropbox and similar. A `.git`
directory and a virtualenv are exactly the kind of large, high-churn tree that
live-sync folders handle badly.
