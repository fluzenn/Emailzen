import sqlite3
import time
from typing import List, Dict

DB = "mail_cache.db"

def init_db():
    with sqlite3.connect(DB) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS headers (
                id TEXT PRIMARY KEY, 
                sender TEXT, 
                subject TEXT, 
                snippet TEXT, 
                ts INTEGER
            )
        """)
        
        # Tentative de migration pour ajouter les colonnes type et email
        try:
            conn.execute("SELECT type, email FROM accounts LIMIT 1")
        except sqlite3.OperationalError:
            # Drop old table and create new
            conn.execute("DROP TABLE IF EXISTS accounts")
            
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                type TEXT DEFAULT 'gmail',
                email TEXT
            )
        """)
        
        # Par défaut, ajouter 'primary' si la table est vide
        cur = conn.execute("SELECT COUNT(*) FROM accounts")
        if cur.fetchone()[0] == 0:
            conn.execute("INSERT INTO accounts (id, type) VALUES ('primary', 'gmail')")
        conn.commit()

def fetch_accounts() -> List[Dict]:
    with sqlite3.connect(DB) as conn:
        cur = conn.execute("SELECT id, type, email FROM accounts")
        return [{"id": row[0], "type": row[1], "email": row[2]} for row in cur.fetchall()]

def add_account(acc_id: str, acc_type: str = "gmail", email: str = None):
    with sqlite3.connect(DB) as conn:
        conn.execute("INSERT OR REPLACE INTO accounts (id, type, email) VALUES (?, ?, ?)", (acc_id, acc_type, email))
        conn.commit()

def upsert_headers(rows: List[Dict]):
    with sqlite3.connect(DB) as conn:
        for r in rows:
            ts = int(time.time())
            conn.execute(
                "REPLACE INTO headers (id,sender,subject,snippet,ts) VALUES (?,?,?,?,?)",
                (r["id"], r["sender"], r["subject"], r.get("snippet",""), ts)
            )
        conn.commit()

def fetch_headers(limit=100) -> List[Dict]:
    with sqlite3.connect(DB) as conn:
        cur = conn.execute("SELECT id,sender,subject,snippet FROM headers ORDER BY ts DESC LIMIT ?", (limit,))
        return [{"id":row[0],"sender":row[1],"subject":row[2],"snippet":row[3]} for row in cur.fetchall()]