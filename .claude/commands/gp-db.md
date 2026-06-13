Query and inspect the GreenPrompt SQLite database.

Database location: `greenprompt_usage.db` in the current working directory or the project root.
Schema defined in: `greenprompt/greenprompt/dbconn.py`

Task: $ARGUMENTS

If no specific task is given, show a database overview:

1. Find the database file:
   ```bash
   find . -name "greenprompt_usage.db" 2>/dev/null | head -5
   ```

2. Show the schema:
   ```bash
   sqlite3 greenprompt_usage.db ".schema prompt_usage"
   ```

3. Show summary statistics:
   ```bash
   sqlite3 greenprompt_usage.db "
   SELECT
     COUNT(*) as total_runs,
     MIN(timestamp) as first_run,
     MAX(timestamp) as last_run,
     ROUND(SUM(energy_wh), 6) as total_energy_wh,
     ROUND(AVG(energy_wh), 6) as avg_energy_wh,
     ROUND(AVG(prompt_score), 1) as avg_prompt_score,
     COUNT(DISTINCT model) as models_used
   FROM prompt_usage;
   "
   ```

4. Show per-model breakdown:
   ```bash
   sqlite3 greenprompt_usage.db "
   SELECT model, COUNT(*) as runs, ROUND(SUM(energy_wh),6) as total_wh,
          ROUND(AVG(total_tokens),0) as avg_tokens
   FROM prompt_usage GROUP BY model ORDER BY total_wh DESC;
   "
   ```

5. Show recent 5 entries (id, timestamp, model, total_tokens, energy_wh, prompt score):
   ```bash
   sqlite3 greenprompt_usage.db "
   SELECT id, timestamp, model, total_tokens,
          ROUND(energy_wh,6), prompt_score
   FROM prompt_usage ORDER BY id DESC LIMIT 5;
   "
   ```

If the task involves adding a column, migrating data, or modifying the schema, read `dbconn.py` first and propose the change carefully — the schema is defined in `init_db()` and the DB may already contain production data.

Known DB path issue: `DB_PATH = os.path.join(os.getcwd(), "greenprompt_usage.db")` means the DB location depends on where Python is run from. If records are missing, check that the correct directory is being used.
