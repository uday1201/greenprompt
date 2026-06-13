Analyze the GreenPrompt energy database and generate a usage report.

The GreenPrompt SQLite database is at `greenprompt_usage.db` in the current working directory (or the project root). The table is `prompt_usage`.

Steps:
1. Find the database: check `./greenprompt_usage.db`, then `~/greenprompt/greenprompt_usage.db`, then `~/greenprompt_usage.db`. Report where it was found.
2. Query the database with `sqlite3` to produce:
   - Total number of prompts logged
   - Total energy consumed (Wh) across all runs
   - Average energy per prompt (Wh)
   - Energy breakdown by model (model name, run count, total Wh, avg Wh per run)
   - Top 5 most energy-intensive prompts (by energy_wh): show id, timestamp, model, total_tokens, energy_wh, and first 80 chars of prompt
   - Top 5 most efficient prompts (lowest energy_wh > 0): same fields
   - Average prompt score (prompt_score) across all runs
   - Energy trend: compare first half vs second half of runs (is usage going up or down?)
   - Time span: date of first run to date of last run
3. Present findings as a clean report with headers. Use concrete numbers, not vague statements.
4. Flag any anomalies: runs with energy_wh = 0 (platform limitation), very long durations (>30s), or very high token counts (>2000 total).
5. Suggest the top 1–2 actions to reduce energy: e.g., use a smaller model, write shorter prompts, improve prompt score.

If the database does not exist or is empty, explain how to set up GreenPrompt and run the first prompt.

User arguments (optional — e.g., a model name or date range to filter on): $ARGUMENTS
