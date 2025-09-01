import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'risk_analysis.db')


@contextmanager
def get_conn():
	conn = sqlite3.connect(DB_PATH, check_same_thread=False)
	conn.row_factory = sqlite3.Row
	try:
		yield conn
		conn.commit()
	except Exception:
		conn.rollback()
		raise
	finally:
		conn.close()


def init_db(drop: bool = False) -> None:
	with get_conn() as conn:
		cur = conn.cursor()
		if drop:
			cur.execute('DROP TABLE IF EXISTS risk_dataset')
		cur.execute('''
			CREATE TABLE IF NOT EXISTS risk_dataset (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				filename TEXT,
				uploaded_at TEXT,
				from_date TEXT,
				to_date TEXT,
				column_a_counts TEXT NOT NULL,
				column_r_counts TEXT NOT NULL,
				risks_rows TEXT NOT NULL
			)
		''')
		# Backwards-compatible migration to add file_b64 column if missing
		cols = {row['name'] for row in cur.execute("PRAGMA table_info('risk_dataset')").fetchall()}
		if 'file_b64' not in cols:
			cur.execute('ALTER TABLE risk_dataset ADD COLUMN file_b64 TEXT')


def save_dataset(filename: str, from_date: str, to_date: str, column_a_counts: Dict[str, int], column_r_counts: Dict[str, int], risks_rows: Any, file_b64: Optional[str] = None) -> None:
	with get_conn() as conn:
		conn.execute(
			'INSERT INTO risk_dataset (filename, uploaded_at, from_date, to_date, column_a_counts, column_r_counts, risks_rows, file_b64) VALUES (?, datetime("now"), ?, ?, ?, ?, ?, ?)',
			(
				filename,
				from_date,
				to_date,
				json.dumps(column_a_counts),
				json.dumps(column_r_counts),
				json.dumps(risks_rows),
				file_b64 or ''
			)
		)


def get_latest_dataset() -> Optional[Dict[str, Any]]:
	with get_conn() as conn:
		row = conn.execute('SELECT filename, uploaded_at, from_date, to_date, column_a_counts, column_r_counts, risks_rows, file_b64 FROM risk_dataset ORDER BY id DESC LIMIT 1').fetchone()
		if not row:
			return None
		return {
			'filename': row['filename'],
			'uploadedAt': row['uploaded_at'],
			'fromDate': row['from_date'],
			'toDate': row['to_date'],
			'columnAData': json.loads(row['column_a_counts'] or '{}'),
			'columnRData': json.loads(row['column_r_counts'] or '{}'),
			'risksRows': json.loads(row['risks_rows'] or '[]'),
			'fileB64': row['file_b64'] or ''
		}


def set_latest_range(from_date: str, to_date: str) -> None:
	with get_conn() as conn:
		row = conn.execute('SELECT id FROM risk_dataset ORDER BY id DESC LIMIT 1').fetchone()
		if not row:
			return
		conn.execute('UPDATE risk_dataset SET from_date=?, to_date=? WHERE id=?', (from_date, to_date, row['id']))