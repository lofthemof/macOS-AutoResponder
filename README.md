# AutoResponder for iMessage

A macOS menu bar app that auto-replies to iMessages from specific contacts.

## Features

- Lives in the menu bar
- Add/remove contacts with per-contact custom reply messages
- Toggle active/inactive from the menu
- Throttles replies per contact (default 30 min) to avoid spam
- Only responds to recent messages (default 1 min age limit)
- Recent activity log visible in menu
- Built-in Full Disk Access prompt + deep-link to System Settings

---

## Prerequisites

- macOS 13+
- Full Disk Access (the app guides you through granting it on first launch)

---

## Installation

1. Download `AutoResponder.dmg` from [Releases](../../releases)
2. Open the DMG and drag AutoResponder to Applications
3. Launch AutoResponder. A 💬 icon will appear in the menu bar
4. On first launch the app will prompt for Full Disk Access and open System Settings automatically

---

## Build from Source

```bash
git clone <repo>
cd macOS-AutoResponder
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Run directly (no .app build needed):
.venv/bin/python3 main.py

# Or build the .dmg:
./build.sh          # outputs dist/AutoResponder.dmg
```

> When running from Terminal, grant Full Disk Access to **Terminal** (not AutoResponder) in System Settings.

---

## Usage

- Click 💬 in the menu bar
- **Add Contact…** → enter a phone number or Apple ID → enter a reply message
- Click a contact to remove it
- Toggle **Active / Inactive** to pause auto-replies
- **Full Disk Access…** → opens System Settings if you need to re-grant access

---

## Configuration (source only)

Edit the constants at the top of `main.py`:

| Constant | Default | Description |
|---|---|---|
| `THROTTLE_SECONDS` | 1800 (30 min) | Min time between replies to the same contact |
| `POLL_INTERVAL` | 2 s | How often the Messages DB is checked |
| `MAX_MESSAGE_AGE` | 60 s | Ignore messages older than this |
