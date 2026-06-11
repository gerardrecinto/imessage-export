#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone

DB_PATH = os.path.expanduser("~/Library/Messages/chat.db")
MAC_EPOCH_OFFSET = 978307200  # seconds between 1970-01-01 and 2001-01-01


# ── iMessage helpers ─────────────────────────────────────────────────────────────

def open_db(path):
    if not os.path.exists(path):
        print(f"error: chat.db not found at {path}", file=sys.stderr)
        print("Terminal needs Full Disk Access:", file=sys.stderr)
        print("  System Settings > Privacy & Security > Full Disk Access", file=sys.stderr)
        sys.exit(1)
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        print(f"error: cannot open chat.db: {e}", file=sys.stderr)
        sys.exit(1)


def mac_ts_to_dt(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts / 1e9 + MAC_EPOCH_OFFSET, tz=timezone.utc).astimezone()


def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def cmd_list(args):
    conn = open_db(DB_PATH)
    rows = conn.execute("""
        SELECT
            c.display_name,
            c.chat_identifier,
            COUNT(m.ROWID)  AS msg_count,
            MAX(m.date)     AS last_date
        FROM chat c
        JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
        JOIN message m             ON m.ROWID = cmj.message_id
        WHERE m.text IS NOT NULL
        GROUP BY c.ROWID
        ORDER BY last_date DESC
    """).fetchall()
    conn.close()

    if not rows:
        print("No conversations found.")
        return

    print(f"{'Contact':<40} {'Messages':>8}  {'Last Message':<16}")
    print("-" * 70)
    for r in rows:
        name = r["display_name"] or r["chat_identifier"] or "(unknown)"
        print(f"{name:<40} {r['msg_count']:>8}  {fmt_dt(mac_ts_to_dt(r['last_date'])):<16}")


def find_chat(conn, query):
    return conn.execute("""
        SELECT ROWID, display_name, chat_identifier
        FROM chat
        WHERE lower(display_name)    LIKE lower(?)
           OR lower(chat_identifier) LIKE lower(?)
    """, (f"%{query}%", f"%{query}%")).fetchall()


def fetch_messages(conn, chat_id, since=None):
    since_ts = 0
    if since:
        try:
            dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            since_ts = int((dt.timestamp() - MAC_EPOCH_OFFSET) * 1e9)
        except ValueError:
            print(f"error: --since must be YYYY-MM-DD, got: {since}", file=sys.stderr)
            sys.exit(1)
    return conn.execute("""
        SELECT m.text, m.is_from_me, m.date, h.id AS sender_id
        FROM message m
        LEFT JOIN handle h         ON h.ROWID = m.handle_id
        JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
        WHERE cmj.chat_id = ?
          AND m.text IS NOT NULL
          AND m.date >= ?
        ORDER BY m.date ASC
    """, (chat_id, since_ts)).fetchall()


def cmd_export(args):
    conn = open_db(DB_PATH)
    matches = find_chat(conn, args.contact)

    if not matches:
        print(f"No conversation found matching: {args.contact}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Multiple matches for '{args.contact}':", file=sys.stderr)
        for m in matches:
            print(f"  {m['display_name'] or m['chat_identifier']}", file=sys.stderr)
        print("Use a more specific name or phone number.", file=sys.stderr)
        sys.exit(1)

    chat = matches[0]
    contact_name = chat["display_name"] or chat["chat_identifier"]
    rows = fetch_messages(conn, chat["ROWID"], since=args.since)
    conn.close()

    if not rows:
        print("No messages found.")
        return

    messages = [
        {
            "timestamp": fmt_dt(mac_ts_to_dt(r["date"])),
            "sender": "Me" if r["is_from_me"] else (r["sender_id"] or contact_name),
            "text": r["text"],
            "is_from_me": bool(r["is_from_me"]),
        }
        for r in rows
    ]

    out = open(args.output, "w", encoding="utf-8") if args.output else sys.stdout
    try:
        if args.format == "txt":
            for m in messages:
                out.write(f"[{m['timestamp']}] {m['sender']}: {m['text']}\n")
        elif args.format == "json":
            json.dump(messages, out, indent=2, ensure_ascii=False)
            out.write("\n")
        elif args.format == "csv":
            writer = csv.DictWriter(out, fieldnames=["timestamp", "sender", "text", "is_from_me"])
            writer.writeheader()
            writer.writerows(messages)
    finally:
        if args.output:
            out.close()
            print(f"Exported {len(messages)} messages to {args.output}")
        else:
            print(f"\n({len(messages)} messages)", file=sys.stderr)


def cmd_stats(args):
    conn = open_db(DB_PATH)
    matches = find_chat(conn, args.contact)

    if not matches:
        print(f"No conversation found matching: {args.contact}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        print(f"Multiple matches for '{args.contact}':", file=sys.stderr)
        for m in matches:
            print(f"  {m['display_name'] or m['chat_identifier']}", file=sys.stderr)
        sys.exit(1)

    chat = matches[0]
    contact_name = chat["display_name"] or chat["chat_identifier"]
    rows = fetch_messages(conn, chat["ROWID"], since=args.since)
    conn.close()

    if not rows:
        print("No messages found.")
        return

    total = len(rows)
    from_me = sum(1 for r in rows if r["is_from_me"])
    from_them = total - from_me
    first_dt = mac_ts_to_dt(rows[0]["date"])
    last_dt = mac_ts_to_dt(rows[-1]["date"])

    dow = Counter(
        mac_ts_to_dt(r["date"]).strftime("%a")
        for r in rows
        if mac_ts_to_dt(r["date"])
    )
    busiest_day = dow.most_common(1)[0][0] if dow else "N/A"

    hour_counts = Counter(
        mac_ts_to_dt(r["date"]).hour
        for r in rows
        if mac_ts_to_dt(r["date"])
    )
    busiest_hour = hour_counts.most_common(1)[0][0] if hour_counts else None
    busiest_hour_str = f"{busiest_hour:02d}:00" if busiest_hour is not None else "N/A"

    print(f"\nConversation: {contact_name}")
    print("─" * 45)
    print(f"  Total messages : {total:,}")
    print(f"  From me        : {from_me:,} ({from_me * 100 // total}%)")
    print(f"  From them      : {from_them:,} ({from_them * 100 // total}%)")
    print(f"  First message  : {fmt_dt(first_dt)}")
    print(f"  Last message   : {fmt_dt(last_dt)}")
    print(f"  Busiest day    : {busiest_day}")
    print(f"  Busiest hour   : {busiest_hour_str}")
    print()


# ── Apple Notes helpers ─────────────────────────────────────────────────────

def run_applescript(script):
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"error: osascript failed: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def strip_html(text):
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def cmd_notes_list(args):
    script = """
    tell application "Notes"
        set output to ""
        repeat with f in folders
            repeat with n in notes of f
                set output to output & name of f & "\t" & name of n & "\t" & (modification date of n as string) & "\n"
            end repeat
        end repeat
        return output
    end tell
    """
    raw = run_applescript(script)
    if not raw:
        print("No notes found.")
        return

    print(f"{'Folder':<25} {'Title':<40} {'Modified'}")
    print("-" * 85)
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            folder, title, modified = parts[0], parts[1], parts[2]
            print(f"{folder:<25} {title:<40} {modified}")


def cmd_notes_export(args):
    if args.folder:
        script = f"""
        tell application "Notes"
            set output to ""
            set f to first folder whose name is "{args.folder}"
            repeat with n in notes of f
                set output to output & "===NOTE===" & name of n & "===BODY===" & body of n & "===END===\n"
            end repeat
            return output
        end tell
        """
        raw = run_applescript(script)
        if not raw:
            print(f"No notes in folder: {args.folder}", file=sys.stderr)
            sys.exit(1)

        out_dir = args.output or "."
        os.makedirs(out_dir, exist_ok=True)
        count = 0
        for chunk in raw.split("===NOTE==="):
            if "===BODY===" not in chunk:
                continue
            title_part, body_part = chunk.split("===BODY===", 1)
            body_part = body_part.split("===END===")[0]
            title = title_part.strip()
            body = body_part if args.format == "html" else strip_html(body_part)
            ext = "html" if args.format == "html" else "txt"
            safe = re.sub(r'[^\w\s-]', '', title).strip().replace(" ", "_")
            path = os.path.join(out_dir, f"{safe}.{ext}")
            with open(path, "w", encoding="utf-8") as f:
                f.write(body)
            count += 1
        print(f"Exported {count} notes to {out_dir}/")

    else:
        if not args.title:
            print("error: provide a note title or use --folder", file=sys.stderr)
            sys.exit(1)
        script = f"""
        tell application "Notes"
            set matches to every note whose name contains "{args.title}"
            if length of matches is 0 then return "NOT_FOUND"
            set n to item 1 of matches
            return name of n & "===BODY===" & body of n
        end tell
        """
        raw = run_applescript(script)
        if raw == "NOT_FOUND" or not raw:
            print(f"No note found matching: {args.title}", file=sys.stderr)
            sys.exit(1)

        if "===BODY===" not in raw:
            print("error: unexpected Notes response", file=sys.stderr)
            sys.exit(1)

        title, body = raw.split("===BODY===", 1)
        content = body if args.format == "html" else strip_html(body)

        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Exported '{title.strip()}' to {args.output}")
        else:
            print(content)


# ── CLI wiring ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="imessage_export",
        description="Export iMessages and Apple Notes from macOS. No subscriptions.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # imessage list
    sub.add_parser("list", help="List all iMessage conversations")

    # imessage export
    exp = sub.add_parser("export", help="Export an iMessage conversation")
    exp.add_argument("contact", help="Contact name or phone number (partial match)")
    exp.add_argument("--format", choices=["txt", "json", "csv"], default="txt")
    exp.add_argument("--since", metavar="YYYY-MM-DD", help="Only messages on or after this date")
    exp.add_argument("--output", metavar="FILE", help="Write to file instead of stdout")

    # imessage stats
    stat = sub.add_parser("stats", help="Show statistics for a conversation")
    stat.add_argument("contact", help="Contact name or phone number (partial match)")
    stat.add_argument("--since", metavar="YYYY-MM-DD", help="Only count messages on or after this date")

    # notes
    notes = sub.add_parser("notes", help="Export Apple Notes")
    notes_sub = notes.add_subparsers(dest="notes_command", required=True)

    notes_sub.add_parser("list", help="List all notes")

    nexp = notes_sub.add_parser("export", help="Export a note or folder of notes")
    nexp.add_argument("title", nargs="?", help="Note title (partial match)")
    nexp.add_argument("--folder", metavar="FOLDER", help="Export all notes in this folder")
    nexp.add_argument("--format", choices=["txt", "html"], default="txt")
    nexp.add_argument("--output", metavar="PATH", help="Output file (single) or directory (--folder)")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "notes":
        if args.notes_command == "list":
            cmd_notes_list(args)
        elif args.notes_command == "export":
            cmd_notes_export(args)


if __name__ == "__main__":
    main()
