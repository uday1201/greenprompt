"""
dbconn.py — SQLite persistence layer for GreenPrompt.

Manages the prompt_usage table: schema creation, inserting prompt run records,
and querying with optional filters.

The database location is resolved once at import by resolve_db_path(), in this
order:

    1. $GREENPROMPT_DB                       — explicit override
    2. DB_PATH in the user config file       — set by `greenprompt setup`
    3. ./greenprompt_usage.db, if it exists  — legacy per-directory database
    4. $GREENPROMPT_HOME/greenprompt_usage.db
    5. ~/.greenprompt/greenprompt_usage.db   — default

Step 3 is what makes the default safe to change: earlier versions computed the
path from os.getcwd() unconditionally, so anyone who already has a database in
a working directory keeps using it exactly as before. Everyone else gets one
stable location, which removes the failure mode where `greenprompt prompt` and
`greenprompt dashboard` run from different directories and silently use
different databases.

All timestamps are stored as UTC ISO 8601 strings. JSON blobs (system_info,
prompt_score_details) are serialized with json.dumps and must be parsed by
callers with json.loads.
"""

import sqlite3
import os
import json
from datetime import datetime, timezone
from greenprompt import constants
from greenprompt.sysUsage import get_system_info

# Path to the SQLite database file
#: Filename used in every candidate location.
DB_FILENAME = "greenprompt_usage.db"


def default_db_dir():
    """Return the directory holding the database when nothing overrides it."""
    home = os.environ.get("GREENPROMPT_HOME")
    if home:
        return os.path.expanduser(home)
    return os.path.join(os.path.expanduser("~"), ".greenprompt")


def resolve_db_path(cwd=None):
    """
    Work out which database file to use. See the module docstring for the order.

    Args:
        cwd: Directory to check for a legacy database. Defaults to os.getcwd().

    Returns:
        An absolute path. The file itself need not exist yet; init_db() creates
        it, along with its parent directory.
    """
    explicit = os.environ.get("GREENPROMPT_DB")
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    configured = constants.load_config().get("DB_PATH")
    if configured:
        return os.path.abspath(os.path.expanduser(configured))

    # A database already sitting in the working directory wins, so upgrading
    # never strands data that earlier versions wrote there.
    legacy = os.path.join(cwd if cwd is not None else os.getcwd(), DB_FILENAME)
    if os.path.exists(legacy):
        return os.path.abspath(legacy)

    return os.path.join(default_db_dir(), DB_FILENAME)


#: Resolved once at import. Reassign this (not the environment) to redirect
#: reads and writes within a running process.
DB_PATH = resolve_db_path()

#: Column order of the prompt_usage table. Kept beside init_db() so callers
#: that need the shape of an empty result set (e.g. analytics.load_usage_data
#: building a DataFrame with no rows) stay in sync with the schema.
PROMPT_USAGE_COLUMNS = (
    "id",
    "timestamp",
    "prompt",
    "prompt_score",
    "prompt_score_details",
    "response",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "energy_estimate_prompt",
    "energy_estimate_tokens",
    "duration_sec",
    "energy_wh",
    "baseline_power_w",
    "baseline_energy_wh",
    "cpu_power_w",
    "gpu_power_w",
    "combined_power_w",
    "system_info",
)


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

    Idempotent — uses CREATE TABLE IF NOT EXISTS, so it is safe to call on
    every read/write path. save_prompt_usage() and get_prompt_usage() both
    call it so that a fresh working directory never raises
    "no such table: prompt_usage".

    Creates the parent directory too: the default location is
    ~/.greenprompt/, which will not exist if `greenprompt setup` never ran.
    """
    parent = os.path.dirname(DB_PATH)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prompt_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            prompt TEXT,
            prompt_score INTEGER,
            prompt_score_details TEXT,
            response TEXT,
            model TEXT,
            prompt_tokens INTEGER,
            completion_tokens INTEGER,
            total_tokens INTEGER,
            energy_estimate_prompt REAL,
            energy_estimate_tokens REAL,
            duration_sec REAL,
            energy_wh REAL,
            baseline_power_w REAL,
            baseline_energy_wh REAL,
            cpu_power_w REAL,
            gpu_power_w REAL,
            combined_power_w REAL,
            system_info TEXT
        )
    """)
    conn.commit()
    conn.close()


def utc_now_iso():
    """
    Return the current UTC time as a naive ISO 8601 string.

    Deliberately naive — no "+00:00" suffix. get_prompt_usage() filters by
    comparing timestamps as strings, so an offset-aware value would not only
    change the format of new rows but would sort inconsistently against every
    row already in the database, silently breaking /api/usage/timeframe.

    This replaces datetime.utcnow(), which is deprecated as of Python 3.12,
    while producing byte-identical output to it.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _first_not_none(data: dict, *keys):
    """Return the first value from data that is not None, checking keys in order."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return None


def save_prompt_usage(data: dict):
    """
    Saves a prompt usage record to the prompt_usage table.
    """
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    system_info = json.dumps(get_system_info())
    cursor.execute(
        """
        INSERT INTO prompt_usage (
            timestamp, prompt, prompt_score, prompt_score_details, response, model, prompt_tokens,
            completion_tokens, total_tokens, energy_estimate_prompt, energy_estimate_tokens, duration_sec, energy_wh,
            baseline_power_w, baseline_energy_wh,
            cpu_power_w, gpu_power_w, combined_power_w, system_info
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            utc_now_iso(),
            data.get("prompt"),
            data.get("prompt_score"),
            json.dumps(data.get("prompt_score_details", {})),
            data.get("response"),
            data.get("model"),
            data.get("prompt_tokens"),
            data.get("completion_tokens"),
            data.get("total_tokens"),
            data.get("energy_estimate_prompt"),
            data.get("energy_estimate_tokens"),
            data.get("duration_sec"),
            _first_not_none(data, "total_energy (Wh)", "energy_wh"),
            _first_not_none(data, "baseline_power (W)", "baseline_power_w"),
            _first_not_none(data, "baseline_energy (Wh)", "baseline_energy_wh"),
            _first_not_none(data, "cpu_power_w (W)", "cpu_power_w"),
            _first_not_none(data, "gpu_power_w (W)", "gpu_power_w"),
            _first_not_none(data, "combined_power_w (W)", "combined_power_w"),
            system_info,
        ),
    )
    conn.commit()
    conn.close()


def get_prompt_usage(start_time=None, end_time=None, model=None):
    """
    Retrieve prompt_usage records with optional filters.

    Args:
        start_time: ISO 8601 string; only rows with timestamp >= this value.
        end_time: ISO 8601 string; only rows with timestamp <= this value.
        model: Exact model name string to filter on (case-sensitive).

    Returns:
        List of dicts, one per row, ordered by timestamp ASC. Each dict has
        all prompt_usage columns. system_info and prompt_score_details are
        JSON strings; callers must parse with json.loads if needed.
    """
    init_db()
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
