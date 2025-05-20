import sqlite3
import os
from datetime import datetime

# Path to the SQLite database file
DB_PATH = os.path.join(os.getcwd(), "greenprompt_usage.db")

def get_connection():
    """
    Returns a new SQLite connection.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """
    Initializes the database and creates the prompt_usage table.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            prompt TEXT,
            response TEXT,
            model TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            duration_sec REAL,
            energy_wh REAL,
            baseline_power_w REAL,
            baseline_energy_wh REAL,
            cpu_power_w REAL,
            gpu_power_w REAL,
            combined_power_w REAL
        )
    """)
    conn.commit()
    conn.close()

def save_prompt_usage(data: dict):
    """
    Saves a prompt usage record to the prompt_usage table.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prompt_usage (
            timestamp, prompt, response, model, prompt_tokens,
            completion_tokens, total_tokens, duration_sec, energy_wh,
            baseline_power_w, baseline_energy_wh,
            cpu_power_w, gpu_power_w, combined_power_w
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        data.get("prompt"),
        data.get("response"),
        data.get("model"),
        data.get("prompt_tokens"),
        data.get("completion_tokens"),
        data.get("total_tokens"),
        data.get("duration_sec"),
        data.get("total_energy (Wh)") or data.get("energy_wh"),
        data.get("baseline_power (W)") or data.get("baseline_power_w"),
        data.get("baseline_energy (Wh)") or data.get("baseline_energy_wh"),
        data.get("cpu_power_w (W)") or data.get("cpu_power_w"),
        data.get("gpu_power_w (W)") or data.get("gpu_power_w"),
        data.get("combined_power_w (W)") or data.get("combined_power_w")
    ))
    conn.commit()
    conn.close()

def get_prompt_usage(start_time=None, end_time=None, model=None):
    """
    Retrieve prompt_usage entries filtered by optional ISO timestamp range and model.
    """
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM prompt_usage"
    conditions = []
    params = []
    if model:
        conditions.append("model = ?")
        params.append(model)
    if start_time:
        conditions.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        conditions.append("timestamp <= ?")
        params.append(end_time)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY timestamp ASC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
