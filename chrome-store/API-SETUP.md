# Publishing from the terminal

Chrome refuses to let any extension script the developer console, so the
browser cannot be driven there. The Chrome Web Store API is the only way to
automate a release.

**What it can do.** Upload the package and submit it for review.

**What it cannot do.** Anything on the store listing. Description,
screenshots, icons, category and the privacy answers are console-only, in
every version of this API. Set those by hand once. After that, a release that
only changes code goes out with one command.

## One-time setup, about ten minutes

You have to do these yourself, because they involve your own Google account.

### 1. Make a project and turn the API on

Open https://console.cloud.google.com/projectcreate and make a project. Call
it anything. Then open
https://console.cloud.google.com/apis/library/chromewebstore.googleapis.com
and press Enable, with that project selected.

### 2. Set up the consent screen, and add yourself as a test user

Google renamed this. It is no longer under APIs and services. It is now
**Google Auth Platform**, and the test user list sits under **Audience**.

https://console.cloud.google.com/auth/audience

Check the project selector at the top matches the project from step 1. Choose
**External**. Fill in the app name and your own email where it asks.

Then, under **Test users**, press Add users and enter
**shivangzephyr@gmail.com**, the account that owns the extension. Save.

Do not skip this. Without it, `auth` fails with `Error 403: access_denied`
and the message that the app has not completed verification, even though you
are the developer. An app in Testing lets nobody in, not even its owner,
unless they are on that list.

Leave it in Testing. It never needs verifying, because you are the only user.
The one catch is that refresh tokens for an app in Testing expire after seven
days. When that happens, run `auth` again. If that becomes annoying, press
Publish app on the consent screen and the tokens stop expiring. Publishing
here only affects the consent screen, not your extension.

### 3. Make the credentials

APIs and services, then Credentials, then Create credentials, then OAuth
client ID. Application type **Desktop app**. Copy the client ID and the client
secret it shows you.

### 4. Grant access

```bash
python3 chrome-store/cws.py auth
```

It asks for the ID and the secret, opens your browser, and you approve. Google
will warn that the app is unverified, which is expected, since it is your own
app used only by you. Press Advanced and continue.

The refresh token is written to `~/.config/overleaf-comments-export/cws.json`
with mode 600. That file is outside the repository and must never be committed.

## Releasing after that

```bash
bash chrome-store/build-zip.sh
python3 chrome-store/cws.py ship
```

`ship` uploads the zip and then asks before submitting. Add `--yes` to skip
the question, once you trust it.

The pieces separately, when you want them.

```bash
python3 chrome-store/cws.py status     # what the store holds right now
python3 chrome-store/cws.py upload     # send the zip, do not submit
python3 chrome-store/cws.py publish    # submit what was already uploaded
python3 chrome-store/cws.py selfcheck  # no credentials needed
```

## When it breaks

**`no refresh token`.** Google only issues one the first time an account
approves an app. Revoke it at https://myaccount.google.com/permissions and run
`auth` again.

**`invalid_grant` after about a week.** The consent screen is still in
Testing. Either run `auth` again or press Publish app on the consent screen.

**`Error 403: access_denied`, has not completed the Google verification
process.** The account is not on the test user list. Add it at
https://console.cloud.google.com/auth/audience under Audience, then Test
users, and check the project selector matches the project holding your OAuth
client. Wait five minutes before retrying, because the list takes a moment to
propagate and an immediate retry shows the same error.

**Upload says FAILURE.** The reason is printed under it. It is nearly always a
version number that is not higher than the one already in the store.
