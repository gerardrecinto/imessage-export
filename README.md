# imessage-export

Export iMessage conversations and Apple Notes from macOS. No subscriptions, no apps, no phone connection.

Reads `~/Library/Messages/chat.db` directly for iMessages and uses the Notes app API for Apple Notes.

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python&logoColor=white)
![macOS](https://img.shields.io/badge/macOS-12%2B-lightgrey?logo=apple)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

---

## How it works

```
iMessages
  ~/Library/Messages/chat.db  (SQLite)
         |
         v
  sqlite3 query
  (message, handle, chat, chat_message_join tables)
         |
         v
  txt / json / csv

Apple Notes
  Notes.app  (via osascript)
         |
         v
  title + HTML body
         |
         v
  txt / html
```

---

## Setup

No dependencies. Python 3.9+ only.

**iMessages only:** Terminal needs Full Disk Access to read chat.db.

```
System Settings > Privacy & Security > Full Disk Access > add Terminal (or iTerm2)
```

**Apple Notes:** No extra permissions. Uses the Notes app API directly.

---

## Usage

### iMessages

```bash
# List all conversations
python imessage_export.py list

# Export a conversation as plain text (default)
python imessage_export.py export "John"

# Export by phone number
python imessage_export.py export "+16191234567"

# Export as JSON
python imessage_export.py export "John" --format json

# Export as CSV
python imessage_export.py export "John" --format csv

# Only messages from a date onward
python imessage_export.py export "John" --since 2024-01-01

# Write to a file instead of stdout
python imessage_export.py export "John" --output thread.txt
```

### Apple Notes

```bash
# List all notes
python imessage_export.py notes list

# Export a note as plain text
python imessage_export.py notes export "Meeting Notes"

# Export as HTML
python imessage_export.py notes export "Meeting Notes" --format html

# Export all notes in a folder
python imessage_export.py notes export --folder "Work" --output ./work-notes/

# Write to a file
python imessage_export.py notes export "Meeting Notes" --output notes.txt
```

---

## Example output

**txt**
```
[2024-06-01 09:14] Me: heading to the office
[2024-06-01 09:15] John: already here
[2024-06-01 09:22] Me: be there in 10
```

**json**
```json
[
  {
    "timestamp": "2024-06-01 09:14",
    "sender": "Me",
    "text": "heading to the office",
    "is_from_me": true
  },
  {
    "timestamp": "2024-06-01 09:15",
    "sender": "+16191234567",
    "text": "already here",
    "is_from_me": false
  }
]
```

---

## Requirements

- Python 3.9+
- macOS 12+
- Full Disk Access for Terminal (iMessages only)

---

## License

MIT
