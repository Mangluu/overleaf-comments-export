# Privacy

This tool has no backend, no account, no analytics and no telemetry. Nothing
you do with it is sent anywhere.

## What it reads

Your Overleaf project: the comment threads, the tracked changes, and the text
of the files that carry a comment. It reads them through the same requests the
Overleaf editor itself makes.

## How it signs in

**The browser extension** uses the Overleaf tab you already have open. It never
reads, stores or transmits your session cookie.

**The Python tool and the desktop app** need a session. You choose how: read
from a browser's cookie store on your own computer, or paste the cookie
yourself. It is kept in memory and forgotten when the program closes, unless
you tick the box that remembers it, which writes it to a settings file on your
own computer.

Your Overleaf password is never asked for and never stored.

## Where the data goes

Into the folder you chose, on your computer. Nowhere else.

## What is written to your computer

- The export itself, in the folder you picked
- A log file, to help work out what went wrong if something does
- Your answers on the form, so it fills itself in next time

The settings file is named at the bottom of the window and you can delete it
whenever you like.

## Your project is never modified

Everything here only reads. It does not post replies, resolve threads, edit
your source, or change anything in your Overleaf project.

## Questions

Open an issue at
https://github.com/Mangluu/overleaf-comments-export/issues
Never paste your session cookie into an issue.
