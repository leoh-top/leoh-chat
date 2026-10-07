# leoh-chat

A rebranded build of [FluffyChat](https://github.com/krille-chan/fluffychat) (Matrix client) preconfigured for the leoh.top chat server. Download: https://chat.leoh.top/download

This repository holds no fork of the FluffyChat source. `rebrand.py` patches a clean upstream checkout (version pinned in `versions.env`):

- name, package id (`top.leoh.chat`), icons, preset homeserver, push gateway
- Android: built-in UnifiedPush distributor (no separate ntfy app), in-app updates
- bot UI: inline buttons (`top.leoh.keyboard`), command menu (`top.leoh.bot_commands` room state), clickable `leoh-cmd:` links
- macOS: ad-hoc signed (no Apple developer account)
- web: served from the site root, fonts proxied through the site

## Build

- macOS and web: GitHub Actions (`.github/workflows/build.yaml`). Push a `v*` tag or run the workflow manually. Artifacts go to GitHub Releases.
- Android: `./build-android.sh`. It needs the Android SDK, JDK 17, rustup and `rsvg-convert`, plus the release signing key in `$LEOH_SIGNING_DIR`.

## License

AGPL-3.0, same as FluffyChat (see `LICENSE`).
