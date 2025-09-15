import Foundation
import SQLite3

// config file related
let dbPath: String = (NSHomeDirectory() as NSString).appendingPathComponent("Library/Messages/chat.db")
let projectDir: String = FileManager.default.currentDirectoryPath
let lastRowFile: String = (projectDir as NSString).appendingPathComponent("last_rowid.txt")
let activeFlagFile: String = (projectDir as NSString).appendingPathComponent("focus.flag")

// Insert contacts here, as well as the autoresponse you want to give to them (phone or Apple ID)
let autoReplyMap: [String: String] = [
    "+11234567890": "Example response: Hey, I'm away right now! Will get back to you soon.",
    "friend@example.com": "Sorry, I’m driving. Will reply soon."
]

// time configs (seconds)
let throttleSeconds: TimeInterval = 60 * 30  
let pollInterval: TimeInterval = 2.0         
let maxMessageAge: TimeInterval = 60 * 1

// state managers
func ensureStateDir() {
    try? FileManager.default.createDirectory(atPath: projectDir, withIntermediateDirectories: true)
}
func readLastRowID() -> Int64 {
    guard let s: String = try? String(contentsOfFile: lastRowFile).trimmingCharacters(in: .whitespacesAndNewlines),
          let v: Int64 = Int64(s) else { return 0 }
    return v
}
func writeLastRowID(_ id: Int64) {
    try? "\(id)".write(toFile: lastRowFile, atomically: true, encoding: .utf8)
}
func isResponderActive() -> Bool {
    FileManager.default.fileExists(atPath: activeFlagFile)
}

// AppleScript helpers
func runAppleScript(_ scriptText: String) -> Bool {
    let tmp: String = (NSTemporaryDirectory() as NSString).appendingPathComponent("autoresp_\(UUID().uuidString).applescript")
    do {
        try scriptText.write(toFile: tmp, atomically: true, encoding: .utf8)
        let p: Process = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        p.arguments = [tmp]
        try p.run()
        p.waitUntilExit()
        try? FileManager.default.removeItem(atPath: tmp)
        return p.terminationStatus == 0
    } catch {
        print("AppleScript run error:", error)
        return false
    }
}

func appleScriptToSend(to handle: String, message: String) -> String {
    let safeHandle: String = handle.replacingOccurrences(of: "\"", with: "\\\"")
    let safeMessage: String = message.replacingOccurrences(of: "\"", with: "\\\"")
    return """
    tell application "Messages"
        set targetService to 1st service whose service type = iMessage
        try
            set theBuddy to buddy "\(safeHandle)" of targetService
            send "\(safeMessage)" to theBuddy
        on error
            set theChats to (chats whose id contains "\(safeHandle)")
            if (count of theChats) > 0 then
                send "\(safeMessage)" to item 1 of theChats
            end if
        end try
    end tell
    """
}

// db helpers
func openDB(_ path: String) -> OpaquePointer? {
    var db: OpaquePointer?
    if sqlite3_open(path, &db) == SQLITE_OK { return db }
    return nil
}

func dateFromiMessage(_ secondsSince2001: Int64) -> Date {
    let referenceDate: Date = Date(timeIntervalSinceReferenceDate: 0) // 01/01/2001
    return referenceDate.addingTimeInterval(TimeInterval(secondsSince2001))
}

func fetchNewMessages(db: OpaquePointer, sinceRowID: Int64) -> [(rowid: Int64, text: String?, handle: String?, date: Int64)] {
    let sql: String = """
      SELECT message.ROWID, message.text, handle.id, message.date
      FROM message
      LEFT JOIN handle ON message.handle_id = handle.ROWID
      WHERE message.is_from_me = 0 AND message.ROWID > ?
      ORDER BY message.ROWID ASC
    """
    var stmt: OpaquePointer?
    var results: [(Int64, String?, String?, Int64)] = []
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
        sqlite3_bind_int64(stmt, 1, sinceRowID)
        while sqlite3_step(stmt) == SQLITE_ROW {
            let rowid: sqlite3_int64 = sqlite3_column_int64(stmt, 0)
            
            var text: String? = nil
            if let c: UnsafePointer<UInt8> = sqlite3_column_text(stmt, 1) {
                text = String(cString: c)
            }

            var handle: String? = nil
            if let c: UnsafePointer<UInt8> = sqlite3_column_text(stmt, 2) {
                handle = String(cString: c)
            }

            let date: sqlite3_int64 = sqlite3_column_int64(stmt, 3)

            results.append((rowid, text, handle, date))
        }
    } else {
        if let err: UnsafePointer<CChar> = sqlite3_errmsg(db) {
            print("SQL error:", String(cString: err))
        }
    }
    sqlite3_finalize(stmt)
    return results
}


func latestRowID(db: OpaquePointer) -> Int64 {
    let sql: String = "SELECT MAX(ROWID) FROM message"
    var stmt: OpaquePointer?
    var result: Int64 = 0
    if sqlite3_prepare_v2(db, sql, -1, &stmt, nil) == SQLITE_OK {
        if sqlite3_step(stmt) == SQLITE_ROW {
            result = sqlite3_column_int64(stmt, 0)
        }
    }
    sqlite3_finalize(stmt)
    return result
}

// ====== Main ======
ensureStateDir()
guard FileManager.default.fileExists(atPath: dbPath) else {
    print("Messages DB not found at \(dbPath).")
    exit(1)
}
guard let db: OpaquePointer = openDB(dbPath) else {
    print("Failed to open DB — check Full Disk Access in System Settings.")
    exit(1)
}

var lastRow: Int64 = readLastRowID()
if lastRow == 0 {
    print("First run: starting at current max ROWID (no history).")
    lastRow = latestRowID(db: db)
    writeLastRowID(lastRow)
}

var lastReplyTime: Date? = nil

print("Watching contacts: \(autoReplyMap.keys.joined(separator: ", "))")
print("AutoResponder active:", isResponderActive())

while true {
    if !isResponderActive() {
        // Skip responding if Focus is off
        Thread.sleep(forTimeInterval: pollInterval)
        continue
    }
    let messages: [(rowid: Int64, text: String?, handle: String?, date: Int64)] = fetchNewMessages(db: db, sinceRowID: lastRow)
    if !messages.isEmpty {
        for m: (rowid: Int64, text: String?, handle: String?, date: Int64) in messages {
            let rowid: Int64 = m.rowid
            let sender: String? = m.handle
            let text: String = m.text ?? ""
            let messageDate: Date = dateFromiMessage(m.date)
            let now: Date = Date()
            if now.timeIntervalSince(messageDate) > maxMessageAge {
                print("[\(Date())] Ignored old message from \(sender ?? "unknown")")
                lastRow = rowid
                writeLastRowID(lastRow)
                continue
            }
            if let h: String = sender, let customMessage = autoReplyMap[h] {
                let canReply: Bool
                if let last: Date = lastReplyTime {
                    canReply = now.timeIntervalSince(last) > throttleSeconds
                } else {
                    canReply = true
                }
                
                if canReply {
                    let script: String = appleScriptToSend(to: h, message: customMessage)
                    let ok: Bool = runAppleScript(script)
                    print("[\(Date())] Replied to \(h): success=\(ok) — message='\(text)'")
                    if ok { lastReplyTime = now }
                } else {
                    print("[\(Date())] Skipped reply to \(h) (throttled).")
                }
            } else {
                if let h: String = sender {
                    print("[\(Date())] Ignored message from \(h).")
                }
            }
            lastRow = rowid
            writeLastRowID(lastRow)
        }
    }
    Thread.sleep(forTimeInterval: pollInterval)
}
