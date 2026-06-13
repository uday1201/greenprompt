Inspect, debug, or work with the GreenPrompt Flask API server.

The API server is defined in `greenprompt/greenprompt/api.py`. It runs on port 5000 by default, started with `sudo greenprompt run`.

Task: $ARGUMENTS

If no specific task is given, perform a health check:

1. Check if the API server is running:
   ```bash
   curl -s http://localhost:5000/api/usage/all | head -c 200
   ```
   If it fails, check if any process is on port 5000: `lsof -i :5000`

2. Check the API log for errors:
   ```bash
   tail -50 /tmp/api.log
   ```

3. Test the core endpoints:
   - GET /api/usage/all  → expect JSON array
   - GET /dashboard      → expect HTML 200

4. Check for the known import bug in api.py:
   Read `greenprompt/greenprompt/api.py` line 1-15.
   The import `from analytics import ...` (line 2) should be `from greenprompt.analytics import ...`.
   Report whether this bug is present and whether it has caused errors in the log.

5. Verify PowerMonitor status:
   The monitor is only initialized on Darwin (macOS). On Linux, it is None.
   Check `constants.OS` and report whether power measurement is active.

6. Report the current state: running/stopped, any errors found, known issues.

Known issues in api.py to be aware of:
- Line 2: `from analytics import` should be `from greenprompt.analytics import`
- Line 130: Ollama proxy URL uses `/ollama/api/` but Ollama's base is `/api/`
- The `monitor` global is None on Linux/Windows, so energy_wh will be 0
