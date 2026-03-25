#!/usr/bin/env python3
import json
import logging
import os
import sqlite3
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone

import rumps

# Config
DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(PROJECT_DIR, "state.json")
LOG_FILE = os.path.join(PROJECT_DIR, "autoresponder.log")

# Time configs (seconds)
THROTTLE_SECONDS = 60 * 30
POLL_INTERVAL = 2.0
MAX_MESSAGE_AGE = 60 * 1

# iMessage stores dates as seconds since 2001-01-01 00:00:00 UTC
IMESSAGE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp()

# In-memory log for the menu (most recent first)
recent_logs: deque[str] = deque(maxlen=5)

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def log(msg: str):
    logging.info(msg)
    recent_logs.appendleft(f"{datetime.now().strftime('%H:%M:%S')}  {msg}")


# State helpers

def read_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": True, "last_rowid": 0, "contacts": {}}


def write_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# iMessage helpers

def run_applescript(script_text):
    tmp = os.path.join(tempfile.gettempdir(), f"autoresp_{uuid.uuid4()}.applescript")
    try:
        with open(tmp, "w") as f:
            f.write(script_text)
        result = subprocess.run(["/usr/bin/osascript", tmp])
        return result.returncode == 0
    except Exception as e:
        log(f"AppleScript error: {e}")
        return False
    finally:
        try:
            os.remove(tmp)
        except FileNotFoundError:
            pass


def applescript_to_send(handle, message):
    safe_handle = handle.replace('"', '\\"')
    safe_message = message.replace('"', '\\"')
    return f'''tell application "Messages"
    set targetService to 1st service whose service type = iMessage
    try
        set theBuddy to buddy "{safe_handle}" of targetService
        send "{safe_message}" to theBuddy
    on error
        set theChats to (chats whose id contains "{safe_handle}")
        if (count of theChats) > 0 then
            send "{safe_message}" to item 1 of theChats
        end if
    end try
end tell'''


def date_from_imessage(seconds_since_2001):
    return IMESSAGE_EPOCH + seconds_since_2001


def fetch_new_messages(conn, since_row_id):
    sql = """
        SELECT message.ROWID, message.text, handle.id, message.date
        FROM message
        LEFT JOIN handle ON message.handle_id = handle.ROWID
        WHERE message.is_from_me = 0 AND message.ROWID > ?
        ORDER BY message.ROWID ASC
    """
    return conn.execute(sql, (since_row_id,)).fetchall()


def latest_row_id(conn):
    row = conn.execute("SELECT MAX(ROWID) FROM message").fetchone()
    return row[0] if row and row[0] is not None else 0


# Menu bar app

class AutoResponderApp(rumps.App):
    def __init__(self):
        super().__init__("💬", quit_button=None)
        self.last_reply_time = None
        self.last_row = 0
        self._lock = threading.Lock()

        # Persistent submenu for recent activity — updated by timer
        self._activity_submenu = rumps.MenuItem("Recent Activity")
        self._activity_submenu.add(self._make_log_item("No activity yet"))

        self._rebuild_menu()
        self._init_db()
        threading.Thread(target=self._poll_loop, daemon=True).start()

    # Menu

    def _rebuild_menu(self):
        self.menu.clear()
        state = read_state()
        active = state.get("active", True)

        self.menu.add(rumps.MenuItem(
            "✅  Active" if active else "❌  Inactive",
            callback=self.toggle_active
        ))
        self.menu.add(None)

        contacts = state.get("contacts", {})
        if contacts:
            for handle, reply in contacts.items():
                preview = reply if len(reply) <= 40 else reply[:40] + "…"
                self.menu.add(rumps.MenuItem(
                    f"{handle}  —  \"{preview}\"",
                    callback=lambda _, h=handle: self._confirm_remove(h)
                ))
        else:
            empty = rumps.MenuItem("No contacts yet")
            empty.set_callback(None)
            self.menu.add(empty)

        self.menu.add(rumps.MenuItem("Add Contact…", callback=self.add_contact))
        self.menu.add(None)
        self.menu.add(self._activity_submenu)
        self.menu.add(rumps.MenuItem("Open Log File…", callback=self.open_log))
        self.menu.add(rumps.MenuItem("Full Disk Access…", callback=self._open_fda_settings))
        self.menu.add(None)
        self.menu.add(rumps.MenuItem("Quit", callback=rumps.quit_application))

    @rumps.timer(3)
    def _refresh_activity(self, _):
        self._activity_submenu.clear()
        if recent_logs:
            for entry in recent_logs:
                self._activity_submenu.add(self._make_log_item(entry))
        else:
            self._activity_submenu.add(self._make_log_item("No activity yet"))

    @staticmethod
    def _make_log_item(title):
        item = rumps.MenuItem(title)
        item.set_callback(None)
        return item

    # Actions

    def toggle_active(self, _):
        with self._lock:
            state = read_state()
            state["active"] = not state.get("active", True)
            write_state(state)
        self._rebuild_menu()

    def add_contact(self, _):
        handle_win = rumps.Window(
            title="Add Contact",
            message="Phone number or Apple ID (e.g. +11234567890 or name@icloud.com):",
            default_text="",
            ok="Next",
            cancel="Cancel",
            dimensions=(320, 24),
        )
        r = handle_win.run()
        if not r.clicked:
            return
        handle = r.text.strip()
        if not handle:
            return

        msg_win = rumps.Window(
            title="Add Contact",
            message=f"Auto-reply message for {handle}:",
            default_text="Hey, I'm away right now! I'll get back to you soon.",
            ok="Add",
            cancel="Cancel",
            dimensions=(320, 24),
        )
        r = msg_win.run()
        if not r.clicked:
            return
        reply = r.text.strip()
        if not reply:
            return

        with self._lock:
            state = read_state()
            state.setdefault("contacts", {})[handle] = reply
            write_state(state)
        log(f"Added contact: {handle}")
        self._rebuild_menu()

    def _confirm_remove(self, handle):
        if rumps.alert(
            title="Remove Contact",
            message=f"Remove auto-reply for {handle}?",
            ok="Remove",
            cancel="Cancel",
        ) == 1:
            with self._lock:
                state = read_state()
                state.get("contacts", {}).pop(handle, None)
                write_state(state)
            log(f"Removed contact: {handle}")
            self._rebuild_menu()

    def open_log(self, _):
        if not os.path.exists(LOG_FILE):
            rumps.alert(title="No log yet", message="No activity has been logged yet.")
            return
        subprocess.run(["open", "-a", "Console", LOG_FILE])

    # DB & polling

    def _init_db(self):
        pass  # DB access handled in _poll_loop with retry

    def _open_fda_settings(self, _=None):
        subprocess.run(["open", "x-apple.systempreferences:"
                        "com.apple.preference.security?Privacy_AllFiles"])

    def _poll_loop(self):
        conn = None
        alerted = False
        while conn is None:
            try:
                if not os.path.exists(DB_PATH):
                    raise FileNotFoundError("chat.db not found")
                conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
                conn.execute("SELECT 1 FROM message LIMIT 1")  # force auth check
            except Exception as e:
                conn = None
                if not alerted:
                    alerted = True
                    log(f"DB access error: {e}")
                    rumps.alert(
                        title="Full Disk Access required",
                        message=(
                            "AutoResponder needs Full Disk Access to read your Messages.\n\n"
                            "System Settings → Privacy & Security → Full Disk Access → "
                            "enable AutoResponder (or Terminal while testing).\n\n"
                            "The app will start automatically once access is granted."
                        )
                    )
                    self._open_fda_settings()
                time.sleep(5)
                continue

        # Initialise last_row
        with self._lock:
            state = read_state()
            self.last_row = state.get("last_rowid", 0)
            if self.last_row == 0:
                self.last_row = latest_row_id(conn)
                state["last_rowid"] = self.last_row
                write_state(state)
        conn.close()

        log(f"AutoResponder started (watching from ROWID {self.last_row})")

        while True:
            time.sleep(POLL_INTERVAL)
            try:
                state = read_state()
                if state.get("active", True):
                    self._process_messages(state)
            except Exception as e:
                log(f"Poll error: {e}")

    def _process_messages(self, state):
        # Open a fresh connection each poll so we always see the latest Messages data.
        # A persistent connection in WAL mode holds a stale read snapshot.
        try:
            conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        except Exception as e:
            log(f"DB connect error: {e}")
            return

        try:
            contacts = state.get("contacts", {})
            messages = fetch_new_messages(conn, self.last_row)
            log(f"Polled — {len(messages)} new message(s), ROWID > {self.last_row}") if messages else None

            for row_id, text, sender, msg_date in messages:
                now = time.time()

                if now - date_from_imessage(msg_date) > MAX_MESSAGE_AGE:
                    log(f"Skipped old message from {sender or 'unknown'}")
                elif sender in contacts:
                    can_reply = (
                        self.last_reply_time is None
                        or now - self.last_reply_time > THROTTLE_SECONDS
                    )
                    if can_reply:
                        ok = run_applescript(applescript_to_send(sender, contacts[sender]))
                        log(f"{'✓ Replied' if ok else '✗ Failed to reply'} to {sender}")
                        if ok:
                            self.last_reply_time = now
                    else:
                        log(f"Throttled — skipped reply to {sender}")
                elif sender:
                    log(f"Ignored message from {sender}")

                self.last_row = row_id
                with self._lock:
                    state["last_rowid"] = row_id
                    write_state(state)
        finally:
            conn.close()


if __name__ == "__main__":
    AutoResponderApp().run()
