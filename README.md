# AutoResponder for iMessage

A macOS SwiftPM tool that automatically replies to iMessages from specific contacts when a custom "Focus" flag is active. Supports per-contact custom messages and throttle control.

## Features

- Auto-reply only to contacts in the `autoReplyMap`.
- Custom message per contact.
- Throttles replies to avoid spamming the same contact.
- Only responds to recent messages (`maxMessageAge` configurable).
- Activation controlled by the presence of a `focus.flag` file.

---

## Prerequisites

- macOS 13+
- Swift 5.9+
- Full Disk Access granted to Terminal/VS Code to access Messages database
- Optional: Xcode if integrating with Focus/Shortcuts automation

---

## Setup & Usage

### 1. Build the project
Open Terminal in your project folder:
```bash
swift build -c release
```

### 2. Run the AutoResponder
Open Terminal in your project folder:
```bash
swift run
```
The program will monitor the Messages database.
It only replies when focus.flag exists in the project folder.

### 3. Activate / Deactivate the auto-responder manually
Enable auto-reply (Focus ON, in your project directory):
```bash
touch focus.flag
```
Disable auto-reply (Focus OFF, in your project directory):
```base
rm focus.flag
```

### 4. Customize contacts and messages
In `main.swift`:
```swift
let autoReplyMap: [String: String] = [
    "+11234567890": "Example response: Hey, I'm away right now! Will get back to you soon.",
    "friend@example.com": "Sorry, I’m driving. Will reply soon."
]
```
- Key: Contact's phone number or Apple ID
- Value: Message to send.

### 5. Adjust behavior (optional)
- `throttleSeconds` — minimum time between replies to the same contact.
- `pollInterval` — how often the program checks for new messages.
- `maxMessageAge` — ignore messages older than this (in seconds).
