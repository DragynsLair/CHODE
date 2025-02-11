import sqlite3
import datetime
from chode.utils import format_timestamp

conn = sqlite3.connect("memories.db")
c = conn.cursor()
c.execute('''
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id TEXT,
    channel_id TEXT,
    user_id TEXT,
    message TEXT,
    timestamp TEXT
)
''')
conn.commit()

def store_memory(server_id, channel_id, user_id, message):
    timestamp = datetime.datetime.utcnow().isoformat()
    c.execute(
        "INSERT INTO memories (server_id, channel_id, user_id, message, timestamp) VALUES (?, ?, ?, ?, ?)",
        (str(server_id), str(channel_id), str(user_id), message, timestamp)
    )
    conn.commit()

def get_recent_conversation(server_id, channel_id, limit=10):
    c.execute(
        "SELECT user_id, message, timestamp FROM memories WHERE server_id=? AND channel_id=? ORDER BY timestamp DESC LIMIT ?",
        (str(server_id), str(channel_id), limit)
    )
    rows = c.fetchall()
    conversation = ""
    for row in reversed(rows):
        conversation += f"User {row[0]} at {format_timestamp(row[2])}: {row[1]}\n"
    return conversation
