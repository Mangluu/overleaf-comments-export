# Submitting, step by step

Everything you paste is in `LISTING.md`. This is the order to do it in.

## Before you start

- [ ] Pay the 5 USD at https://chrome.google.com/webstore/devconsole
      signed in as **shivangzephyr@gmail.com**. One-time, per account.
- [ ] Take the screenshots. See the Screenshots section of `LISTING.md`.
      At least one, 1280x800. This is the only part nobody but you can do,
      so do it first or it will be what holds the submission up.

## Upload

- [ ] Rebuild the package so it matches the current code:
      `bash chrome-store/build-zip.sh`
- [ ] New item, upload `chrome-store/extension.zip`.

## Store listing tab

- [ ] Item name, summary, description — from `LISTING.md`
- [ ] Category: Workflow & Planning
- [ ] Language: English (United States)
- [ ] Upload the screenshots, best one first

## Privacy tab

This is the part reviewers actually read.

- [ ] Single purpose
- [ ] Justify activeTab, scripting, downloads — one sentence each
- [ ] Remote code: **No, I am not using remote code**
- [ ] Data usage: tick **Website content** only
- [ ] Tick all three certifications
- [ ] Privacy policy URL:
      https://github.com/Mangluu/overleaf-comments-export/blob/main/PRIVACY.md

## Distribution

- [ ] Visibility: Public
- [ ] Regions: all

## Submit

- [ ] Submit for review. Days, sometimes longer.

## Once it is published

- [ ] Send me the store URL and I will update the README and the extension
      guide to point at it instead of at loading an unpacked folder, and add
      it to the PyPI page.

## If it is rejected

Do not panic and do not rewrite everything. Rejections here are nearly always
about one permission, and the reply is to restate the single purpose in the
same plain words. Send me what they said and I will draft the response.
