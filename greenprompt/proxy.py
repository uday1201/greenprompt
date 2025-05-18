from flask import Flask, request, jsonify
import requests
import sqlite3
import time
from datetime import datetime

# Configure ports
PROXY_PORT = 11434
OLLAMA_BACKEND = "http://localhost:11435/api/generate"
DB_FILE = "usage_log.db"

# Create and configure Flask app
app = Flask(__name__)

# Initialize SQLite DB
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            model TEXT,
            prompt TEXT,
            response TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            duration REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.route("/api/generate", methods=["POST"])
def proxy_generate():
    payload = request.get_json()
    prompt = payload.get("prompt", "")
    model = payload.get("model", "")
    start = time.time()

    try:
        response = requests.post(OLLAMA_BACKEND, json=payload)
        data = response.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    end = time.time()
    duration = end - start
    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    total_tokens = prompt_tokens + completion_tokens

    # Store in DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO prompts (timestamp, model, prompt, response, prompt_tokens, completion_tokens, total_tokens, duration)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.now().isoformat(), model, prompt, data.get("response", ""),
        prompt_tokens, completion_tokens, total_tokens, duration
    ))
    conn.commit()
    conn.close()

    return jsonify(data)

if __name__ == "__main__":
    print(f"🔁 GreenPrompt proxy running on http://localhost:{PROXY_PORT} → forwarding to Ollama on 11435")
    app.run(port=PROXY_PORT)