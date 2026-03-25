#!/usr/bin/env python3
import os
import sqlite3
import subprocess
import tempfile
import time
import uuid
from datetime import datetime, timezone

# Config
DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
LAST_ROW_FILE = os.path.join(PROJECT_DIR, "last_rowid.txt")
ACTIVE_FLAG_FILE = os.path.join(PROJECT_DIR, "focus.flag")

# Insert contacts here, as well as the autoresponse you want to give to them (phone or Apple ID)
AUTO_REPLY_MAP = {
    "+11234567890": "Example response: Hey, I'm away right now! Will get back to you soon.",
    "friend@example.com": "Sorry, I'm driving. Will reply soon.",
}

# Time configs (seconds)
THROTTLE_SECONDS = 60 * 30
POLL_INTERVAL = 2.0
MAX_MESSAGE_AGE = 60 * 1

# iMessage stores dates as seconds since 2001-01-01 00:00:00 UTC
IMESSAGE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc).timestamp()


def read_last_row_id():
    try:
        with open(LAST_ROW_FILE) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return 0


def write_last_row_id(row_id):
    with open(LAST_ROW_FILE, "w") as f:
        f.write(str(row_id))


def is_responder_active():
    return os.path.exists(ACTIVE_FLAG_FILE)


def run_applescript(script_text):
    tmp = os.path.join(tempfile.gettempdir(), f"autoresp_{uuid.uuid4()}.applescript")
    try:
        with open(tmp, "w") as f:
            f.write(script_text)
        result = subprocess.run(["/usr/bin/osascript", tmp])
        return result.returncode == 0
    except Exception as e:
        print("AppleScript run error:", e)
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


def main():
    if not os.path.exists(DB_PATH):
        print(f"Messages DB not found at {DB_PATH}.")
        return

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)

    last_row = read_last_row_id()
    if last_row == 0:
        print("First run: starting at current max ROWID (no history).")
        last_row = latest_row_id(conn)
        write_last_row_id(last_row)

    last_reply_time = None

    print(f"Watching contacts: {', '.join(AUTO_REPLY_MAP.keys())}")
    print(f"AutoResponder active: {is_responder_active()}")

    while True:
        if not is_responder_active():
            time.sleep(POLL_INTERVAL)
            continue

        messages = fetch_new_messages(conn, last_row)
        for row_id, text, sender, msg_date in messages:
            now = time.time()
            message_ts = date_from_imessage(msg_date)

            if now - message_ts > MAX_MESSAGE_AGE:
                print(f"[{datetime.now()}] Ignored old message from {sender or 'unknown'}")
                last_row = row_id
                write_last_row_id(last_row)
                continue

            if sender in AUTO_REPLY_MAP:
                can_reply = last_reply_time is None or (now - last_reply_time > THROTTLE_SECONDS)
                if can_reply:
                    script = applescript_to_send(sender, AUTO_REPLY_MAP[sender])
                    ok = run_applescript(script)
                    print(f"[{datetime.now()}] Replied to {sender}: success={ok} — message='{text or ''}'")
                    if ok:
                        last_reply_time = now
                else:
                    print(f"[{datetime.now()}] Skipped reply to {sender} (throttled).")
            elif sender:
                print(f"[{datetime.now()}] Ignored message from {sender}.")

            last_row = row_id
            write_last_row_id(last_row)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
