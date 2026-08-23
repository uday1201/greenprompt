"""
cli.py — GreenPrompt command-line interface.

Entry point for the `greenprompt`, `gprompt`, and `greenp` commands. Parses
subcommands and delegates to either the running API server (for prompt/monitor)
or directly to module functions (for score). Server lifecycle (run/stop) is
managed by spawning processes and, when stopping, signalling only processes
that are verified to be GreenPrompt API servers.

Subcommands: setup, run, prompt, monitor, score, dashboard, stop, log_api,
migrate.
See README.md for full usage examples and flag reference.

Sudo policy: no greenprompt command requires the caller to be root. On macOS,
powermetrics requires root — samplerMac.py calls `sudo powermetrics`
internally. Run `sudo $(command -v greenprompt) setup` once to configure
passwordless sudo
for powermetrics; thereafter all commands run as a normal user.
"""

import argparse
import os
import requests
import sys
import subprocess
import webbrowser
from greenprompt.dbconn import get_prompt_usage
from greenprompt.scoreBasic import score_prompt


#: Substring that identifies a GreenPrompt API server in a process command
#: line. `greenprompt run` spawns `python -m greenprompt.api --port=N`, so this
#: appears in the command line of every server we start.
API_PROCESS_MARKER = "greenprompt.api"


def listening_pids(port):
    """
    Return the PIDs of processes *listening* on `port`.

    Uses `lsof -sTCP:LISTEN -t`, which prints one PID per line and nothing
    else. The previous implementation parsed the second line of plain `lsof
    -i :PORT` output, which also matches established connections *to* that
    port — so the PID it picked was not reliably the listener.

    Returns an empty list if lsof is unavailable (notably on Windows) or
    reports nothing, rather than raising.
    """
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return []
    return [line.strip() for line in result.stdout.split() if line.strip().isdigit()]


def is_greenprompt_api(pid):
    """
    Return True if `pid` looks like a GreenPrompt API server.

    Checked before sending any signal. Without this, `greenprompt run --port
    5432` would kill Postgres and `--port 3000` would kill whatever dev server
    happened to be there — the old code killed whatever owned the port.
    """
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
        )
    except (OSError, ValueError):
        return False
    return API_PROCESS_MARKER in result.stdout


def stop_api(port, quiet=False):
    """
    Stop GreenPrompt API servers listening on `port`.

    Only processes that `is_greenprompt_api()` recognises are signalled;
    anything else is reported and left alone. Sends SIGTERM rather than
    SIGKILL so the power sampler thread gets a chance to shut down.

    Args:
        port: Port to look at.
        quiet: Suppress the "nothing found" message.

    Returns:
        List of PIDs that were signalled.
    """
    killed = []
    for pid in listening_pids(port):
        if not is_greenprompt_api(pid):
            print(
                f"Refusing to kill PID {pid} on port {port}: it is not a "
                f"GreenPrompt API server. Choose a different port."
            )
            continue
        try:
            subprocess.run(["kill", str(pid)], check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            print(f"Could not stop PID {pid}: {e}")
            continue
        print(f"Stopped GreenPrompt API server on port {port} (PID {pid}).")
        killed.append(pid)

    if not killed and not quiet:
        print(f"No GreenPrompt API server found listening on port {port}.")
    return killed


def run_api(port):
    """
    Start the GreenPrompt Flask API server as a background subprocess.

    Any GreenPrompt server already on `port` is stopped first. If the port is
    held by something that is *not* a GreenPrompt server, this refuses to start
    rather than killing it.

    Args:
        port: Integer port number to bind the Flask server to.

    Returns:
        The Popen handle, or None if the port was occupied by a foreign process.
    """
    foreign = [pid for pid in listening_pids(port) if not is_greenprompt_api(pid)]
    if foreign:
        print(
            f"Port {port} is in use by another process (PID {', '.join(foreign)}). "
            f"Not starting. Pick another port with --port."
        )
        return None

    stop_api(port, quiet=True)

    proc = subprocess.Popen(
        [sys.executable, "-m", "greenprompt.api", f"--port={port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"API server is running on port {port} in the background.")
    return proc


def main():
    parser = argparse.ArgumentParser(
        prog="greenprompt",
        description="GreenPrompt CLI: track energy usage of LLM prompts",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup command
    p_setup = subparsers.add_parser(
        "setup",
        help="Write the user config, download NLTK data, verify Ollama, initialize the database",
    )
    p_setup.add_argument(
        "--ollama-port",
        type=int,
        default=11434,
        help="Port for the Ollama server (default: 11434)",
    )
    # run command
    p_run = subparsers.add_parser("run", help="Start the web API server and dashboard")
    p_run.add_argument(
        "--port", type=int, default=5000, help="Port for the web server (default: 5000)"
    )
    # prompt command
    p_prompt = subparsers.add_parser(
        "prompt", help="Send a prompt and display energy/token stats"
    )
    p_prompt.add_argument("prompt", type=str, help="The prompt text to send")
    p_prompt.add_argument(
        "--model",
        type=str,
        default="llama3.2:latest",
        help="Model to use (default: llama3.2:latest)",
    )
    p_prompt.add_argument(
        "--port", type=int, default=5000, help="API server port (default: 5000)"
    )
    # monitor command
    p_mon = subparsers.add_parser(
        "monitor", help="Display the last N prompt usage entries"
    )
    p_mon.add_argument(
        "--count", type=int, default=10, help="Number of entries to show (default: 10)"
    )
    # log_api command (optional)
    p_log = subparsers.add_parser("log_api", help="Tail the API server logs")
    p_log.add_argument(
        "--follow", action="store_true", help="Follow the log output (default: False)"
    )

    # dashboard command
    p_dash = subparsers.add_parser(
        "dashboard", help="Open the dashboard in your browser"
    )
    p_dash.add_argument(
        "--port", type=int, default=5000, help="API server port (default: 5000)"
    )

    # stop command
    p_stop = subparsers.add_parser("stop", help="Stop the API server")
    p_stop.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port where the API server is running (default: 5000)",
    )

    # migrate command
    p_migrate = subparsers.add_parser(
        "migrate",
        help="Merge databases left by older versions into the one in use",
    )
    p_migrate.add_argument(
        "--from",
        dest="sources",
        action="append",
        metavar="PATH",
        help="Database to merge (repeatable). Skips discovery when given.",
    )
    p_migrate.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be merged without writing anything",
    )
    p_migrate.add_argument(
        "-y", "--yes", action="store_true", help="Do not prompt for confirmation"
    )

    # score command
    p_score = subparsers.add_parser(
        "score", help="Score a prompt using the built-in scoring function"
    )
    p_score.add_argument("prompt", type=str, help="The prompt text to score")

    args = parser.parse_args()

    if args.command == "setup":
        from greenprompt.setup import main as setup_main

        setup_main()
        print("✅ Setup complete: config written and database initialized")

    elif args.command == "run":
        print(f"Starting API server on port {args.port}...")
        run_api(port=args.port)

    elif args.command == "prompt":
        # Make api call to run the prompt
        print("Running prompt...")
        url = f"http://127.0.0.1:{args.port}/api/prompt"
        payload = {"prompt": args.prompt, "model": args.model}
        try:
            response = requests.post(url, json=payload)
            data = response.json()
            if "error" in data:
                print(f"Error: {data['error']}")
                sys.exit(1)
            print("\nResponse:\n" + data.get("response", ""))
            print("\n--- Prompt usage data ---")
            print(f"Prompt tokens: {data.get('prompt_tokens')}")
            print(f"Completion tokens: {data.get('completion_tokens')}")
            print(f"Total tokens: {data.get('total_tokens')}")
            print(f"Duration (sec): {data.get('duration_sec')}")
            print(f"Baseline power (W): {data.get('baseline_power (W)')}")
            print(f"Baseline energy (Wh): {data.get('baseline_energy (Wh)')}")
            print(f"CPU power (W): {data.get('cpu_power_w (W)')}")
            print(f"GPU power (W): {data.get('gpu_power_w (W)')}")
            print(f"Combined power (W): {data.get('combined_power_w (W)')}")
            print(f"Energy used (Wh): {data.get('total_energy (Wh)')}")
            if data.get("saved") is False:
                print(
                    "\n⚠️  This run was NOT saved to the database:\n"
                    f"    {data.get('save_error', 'unknown error')}\n"
                    "    It will not appear in `greenprompt monitor` or the dashboard."
                )
        except requests.exceptions.ConnectionError:
            print(f"Error: cannot connect to API server on port {args.port}.")
            print(f"Start it first with: greenprompt run --port {args.port}")
            sys.exit(1)
        except Exception as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "monitor":
        entries = get_prompt_usage(start_time=None, end_time=None, model=None)
        for entry in entries[-args.count :]:
            print(f"Timestamp: {entry['timestamp']}")
            print(f"Prompt: {entry['prompt']}")
            print(f"Response: {entry['response']}")
            print(f"Model: {entry['model']}")
            print(f"Prompt tokens: {entry['prompt_tokens']}")
            print(f"Completion tokens: {entry['completion_tokens']}")
            print(f"Total tokens: {entry['total_tokens']}")
            print(f"Duration (sec): {entry['duration_sec']}")
            print(f"Energy (Wh): {entry['energy_wh']}")
            print("-" * 40)
        print(f"Displayed the last {args.count} entries.")

    elif args.command == "log_api":
        print("Tailing the API logs...")
        try:
            subprocess.run(["tail", "-f", "/tmp/api.log"], check=True)
        except KeyboardInterrupt:
            print("\nStopped tailing the API logs.")

    elif args.command == "dashboard":
        print("Starting the dashboard...")
        url = f"http://localhost:{args.port}/dashboard"
        try:
            webbrowser.open(url)
        except Exception as e:
            print(f"Error opening dashboard: {e}")
            print(f"Open manually: {url}")

    elif args.command == "stop":
        print(f"Stopping API server on port {args.port}...")
        stop_api(args.port)
    elif args.command == "migrate":
        import sqlite3

        from greenprompt.dbconn import (
            DB_PATH,
            find_databases,
            merge_database,
        )

        from greenprompt.dbconn import DatabaseNotWritable, check_writable

        target = DB_PATH
        print(f"Merging into {target}")
        try:
            check_writable(target)
        except DatabaseNotWritable as e:
            # The unwritable file is the target, not any source; saying so once
            # beats repeating SQLite's message for every source we try.
            print(f"\nError: {e}")
            sys.exit(1)

        sources = args.sources
        if sources:
            sources = [
                s for s in sources if os.path.abspath(s) != os.path.abspath(target)
            ]
        else:
            print("Searching for other databases…")
            sources = find_databases()

        if not sources:
            print("No other GreenPrompt databases found. Nothing to do.")
            return

        # Report before touching anything, so --dry-run and the confirmation
        # prompt show the same numbers the real run will use.
        planned = []
        for src in sources:
            try:
                count = merge_database(src, dry_run=True)
            except (ValueError, sqlite3.Error) as e:
                # One unreadable or incompatible database must not abort the
                # rest of the merge.
                print(f"  skipping {src}: {e}")
                continue
            planned.append((src, count))
            print(f"  {src}: {count} new row(s)")

        total = sum(c for _, c in planned)
        if total == 0:
            print("Everything is already merged. Nothing to do.")
            return
        if args.dry_run:
            print(f"Dry run: {total} row(s) would be merged. Nothing was written.")
            return
        if not args.yes:
            reply = input(f"Merge {total} row(s) into {target}? [y/N] ")
            if reply.strip().lower() not in ("y", "yes"):
                print("Aborted; nothing was changed.")
                return

        merged = 0
        for src, _ in planned:
            try:
                merged += merge_database(src)
            except (ValueError, sqlite3.Error) as e:
                print(f"  failed to merge {src}: {e}")
        print(f"Merged {merged} row(s). Sources were left untouched.")
        print("Re-running this is safe: already-merged rows are skipped.")

    elif args.command == "score":
        # Takes a prompt as a parameter (string) and returns the score
        parser = argparse.ArgumentParser()
        parser.add_argument("prompt", type=str, help="The prompt text to score")
        parsed_args, _ = parser.parse_known_args(sys.argv[2:])
        prompt = parsed_args.prompt
        try:
            score = score_prompt(prompt)
            print(f"Score for the prompt: {score}")
        except Exception as e:
            print(f"Error scoring prompt: {e}")


if __name__ == "__main__":
    main()
