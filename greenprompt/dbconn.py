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
    """
    Return the directory holding the database when nothing overrides it.

    Uses the invoking user's home rather than "~" so that `sudo greenprompt
    setup` creates the database for the user who ran it, not for root.
    """
    home = os.environ.get("GREENPROMPT_HOME")
    if home:
        return os.path.expanduser(home)
    return os.path.join(constants.invoking_user_home(), ".greenprompt")


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


class DatabaseNotWritable(RuntimeError):
    """
    The database exists but cannot be written to.

    Raised in place of SQLite's "attempt to write a readonly database", which
    names neither the file nor the remedy. The overwhelmingly common cause is a
    file created by an old `sudo greenprompt run` and left owned by root, after
    which every non-root command fails to save.
    """


def check_writable(path=None):
    """
    Raise DatabaseNotWritable if `path` exists but cannot be written.

    Checked explicitly rather than left to SQLite so the message can name the
    file and say how to fix it.
    """
    path = path or DB_PATH
    if not os.path.exists(path):
        return
    if os.access(path, os.W_OK):
        return

    owner = ""
    try:
        import pwd

        owner = pwd.getpwuid(os.stat(path).st_uid).pw_name
    except Exception:  # noqa: BLE001 — best-effort detail for the message
        pass

    me = os.environ.get("USER") or "$(whoami)"
    owned_by = f" It is owned by {owner}." if owner and owner != me else ""
    raise DatabaseNotWritable(
        f"Cannot write to {path}.{owned_by}\n"
        f"  Prompts will not be saved until this is fixed. To take ownership:\n"
        f"      sudo chown {me} {path}\n"
        f"  Or point GreenPrompt at a different file with $GREENPROMPT_DB."
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
    existed = os.path.exists(DB_PATH)
    check_writable()
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
    # Both columns get filtered on by get_prompt_usage(), and timestamp also
    # orders every result. IF NOT EXISTS keeps init_db() idempotent.
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_usage_timestamp "
        "ON prompt_usage (timestamp)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_usage_model ON prompt_usage (model)"
    )
    conn.commit()
    conn.close()

    # A database created by `sudo greenprompt setup` would otherwise be owned
    # by root and unwritable by the user for every command afterwards.
    if not existed:
        constants.give_to_invoking_user(DB_PATH)
        if parent:
            constants.give_to_invoking_user(parent)


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
    # run_prompt() has already gathered this and passes it through; only
    # compute it again for callers that did not. It costs ~40ms.
    system_info = data.get("system_info")
    if not isinstance(system_info, dict):
        system_info = get_system_info()
    system_info = json.dumps(system_info)
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


#: Columns copied when merging databases. `id` is excluded so merged rows get
#: fresh autoincrement keys instead of colliding with existing ones.
_MERGE_COLUMNS = tuple(c for c in PROMPT_USAGE_COLUMNS if c != "id")

#: Identity of a row for merge purposes. Timestamps carry microseconds, so this
#: distinguishes rows without needing a schema change or a stored hash.
_IDENTITY_COLUMNS = ("timestamp", "prompt", "model")


def is_usage_database(path):
    """True if `path` is a readable SQLite file containing a prompt_usage table."""
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return False
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='prompt_usage'"
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def find_databases(search_roots=None, max_depth=3, exclude=None):
    """
    Look for GreenPrompt databases other than the one in use.

    Older versions resolved the database path from the working directory, so a
    user can easily have several. Searching is bounded by depth and skips
    hidden and dependency directories, because walking a whole home directory
    is slow and mostly pointless.

    Args:
        search_roots: Directories to search. Defaults to the invoking user's
            home and the current directory.
        max_depth: How far below each root to descend.
        exclude: Paths to leave out. Defaults to the database in use.

    Returns:
        Sorted list of absolute paths that hold a prompt_usage table.
    """
    if search_roots is None:
        search_roots = [constants.invoking_user_home(), os.getcwd()]
    excluded = {
        os.path.abspath(p) for p in (exclude if exclude is not None else [DB_PATH])
    }

    skip = {".git", "node_modules", "venv", ".venv", "__pycache__", "Library", ".Trash"}
    found = set()
    for root in search_roots:
        root = os.path.abspath(os.path.expanduser(root))
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None):
            if dirpath.count(os.sep) - base_depth >= max_depth:
                dirnames[:] = []
            dirnames[:] = [
                d for d in dirnames if d not in skip and not d.startswith(".")
            ]
            if DB_FILENAME in filenames:
                candidate = os.path.join(dirpath, DB_FILENAME)
                if candidate not in excluded and is_usage_database(candidate):
                    found.add(candidate)
    return sorted(found)


def _table_columns(conn, schema):
    """Column names of prompt_usage in an attached schema, in declared order."""
    return [row[1] for row in conn.execute(f"PRAGMA {schema}.table_info(prompt_usage)")]


def merge_database(source_path, dry_run=False):
    """
    Copy rows from `source_path` into the database in use.

    Idempotent: a row whose identity already exists is skipped, so running a
    merge twice adds nothing the second time. The source is opened read-only
    and is never modified or removed.

    Schemas are intersected rather than assumed to match. The table has gained
    columns over time — `prompt_score` and `prompt_score_details` arrived with
    prompt scoring, `energy_estimate_*` later still — so a database written by
    an older version genuinely has fewer columns, and those are exactly the
    databases worth merging. Only columns present in both are copied; the rest
    are left NULL.

    Args:
        source_path: Database to read from.
        dry_run: Count what would be copied without writing anything.

    Returns:
        Number of rows copied, or that would be copied under dry_run.

    Raises:
        ValueError: If the source is not a readable GreenPrompt database, or
            shares no usable columns with the current schema.
    """
    source_path = os.path.abspath(os.path.expanduser(source_path))
    if source_path == os.path.abspath(DB_PATH):
        return 0
    if not is_usage_database(source_path):
        raise ValueError(f"{source_path} is not a readable GreenPrompt database")

    init_db()
    conn = get_connection()
    try:
        conn.execute("ATTACH DATABASE ? AS src", (f"file:{source_path}?mode=ro",))
    except sqlite3.Error:
        conn.execute("ATTACH DATABASE ? AS src", (source_path,))
    try:
        source_columns = set(_table_columns(conn, "src"))
        target_columns = set(_table_columns(conn, "main"))
        shared = [
            c for c in _MERGE_COLUMNS if c in source_columns and c in target_columns
        ]
        if not shared:
            raise ValueError(f"{source_path} shares no columns with the current schema")

        # Identify rows by whichever identity columns the source actually has.
        # Timestamps carry microseconds, so even timestamp alone is specific.
        identity = [c for c in _IDENTITY_COLUMNS if c in source_columns]
        if not identity:
            raise ValueError(f"{source_path} has no timestamp column to match on")

        # `IS` rather than `=` so that NULL matches NULL; older rows have gaps.
        predicate = " AND ".join(f"m.{c} IS s.{c}" for c in identity)
        where_new = (
            f"WHERE NOT EXISTS (SELECT 1 FROM main.prompt_usage m WHERE {predicate})"
        )
        columns = ", ".join(shared)

        pending = conn.execute(
            f"SELECT COUNT(*) FROM src.prompt_usage s {where_new}"
        ).fetchone()[0]
        if pending and not dry_run:
            conn.execute(
                f"INSERT INTO main.prompt_usage ({columns}) "
                f"SELECT {columns} FROM src.prompt_usage s {where_new}"
            )
            conn.commit()
    finally:
        conn.execute("DETACH DATABASE src")
        conn.close()
    return pending


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
