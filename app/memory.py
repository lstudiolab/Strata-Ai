import sqlite3
from pathlib import Path
class Memory:
 def __init__(self,path):
  self.path=path;Path(path).parent.mkdir(parents=True,exist_ok=True)
  with sqlite3.connect(path) as d:
   d.execute('CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,first_question TEXT)')
   d.execute('CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY AUTOINCREMENT,session_id TEXT,role TEXT,content TEXT)')
 def first(self,sid):
  with sqlite3.connect(self.path) as d:
   x=d.execute('SELECT first_question FROM sessions WHERE id=?',(sid,)).fetchone();return x[0] if x else None
 def start(self,sid,first):
  with sqlite3.connect(self.path) as d:d.execute('INSERT OR IGNORE INTO sessions VALUES(?,?)',(sid,first))
 def add(self,sid,role,text):
  with sqlite3.connect(self.path) as d:d.execute('INSERT INTO messages(session_id,role,content) VALUES(?,?,?)',(sid,role,text))
 def history(self,sid,n=20):
  with sqlite3.connect(self.path) as d:return list(reversed(d.execute('SELECT role,content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?',(sid,n)).fetchall()))
