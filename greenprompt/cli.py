import argparse
import os
import requests
import sys
import subprocess
from greenprompt.dbconn import get_prompt_usage
import importlib.util


def run_api(port):
    """
    Run the API server on the specified port.
    """
    # Check if the port is in use
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}"], capture_output=True, text=True
        )
        if result.stdout:
            print(f"Port {port} is in use. Killing the process...")
            # Extract the process ID (PID) and kill it
            pid = result.stdout.splitlines()[1].split()[1]
            subprocess.run(["kill", "-9", pid], check=True)
            print(f"Process on port {port} has been killed.")
    except Exception as e:
        print(f"Error checking or killing process on port {port}: {e}")

    # Start the API server
    api_path = importlib.util.find_spec("greenprompt.api").origin
    subprocess.Popen(
        [sys.executable, api_path, f"--port={port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"API server is running on port {port} in the background.")


def main():
    parser = argparse.ArgumentParser(
        prog="greenprompt",
        description="GreenPrompt CLI: track energy usage of LLM prompts on macOS",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # setup command
    p_setup = subparsers.add_parser(
        "setup",
        help="Install and configure Ollama, initialize database, generate constants",
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
        "--model", type=str, default="llama2", help="Model to use (default: llama2)"
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
    subparsers.add_parser("dashboard", help="Open the dashboard in your browser")

    # stop command
    p_stop = subparsers.add_parser("stop", help="Stop the API server")
    p_stop.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port where the API server is running (default: 5000)",
    )

    args = parser.parse_args()

    if args.command == "setup":
        # Verify sudo privileges
        if os.geteuid() != 0:
            print(
                "Error: 'setup' requires sudo privileges. Please run 'sudo greenprompt setup'"
            )
            sys.exit(1)
        # Run setup.py file
        from greenprompt.setup import main as setup_main

        setup_main()
        print("✅ Setup complete: database initialized and constants saved")

    elif args.command == "run":
        # Verify sudo privileges
        if os.geteuid() != 0:
            print(
                "Error: 'run' requires sudo privileges. Please run 'sudo greenprompt run'"
            )
            sys.exit(1)
        print(f"Starting API server on port {args.port}...")
        run_api(port=args.port)

    elif args.command == "prompt":
        # Make api call to run the prompt
        print("Running prompt...")
        url = "http://127.0.0.1:5000/api/prompt"
        payload = {"prompt": args.prompt, "model": args.model}
        try:
            response = requests.post(url, json=payload)
            data = response.json()
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
        except Exception as e:
            print(f"Error connecting to API: {e}")
            print("Is the API server running? Try 'sudo greenprompt run'.")

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
        # Open a tab in a web browser at http://localhost:5000/dashboard
        try:
            subprocess.run(["open", "http://localhost:5000/dashboard"], check=True)
        except Exception as e:
            print(f"Error opening dashboard: {e}")

    elif args.command == "stop":
        # Verify sudo privileges
        if os.geteuid() != 0:
            print(
                "Error: 'stop' requires sudo privileges. Please run 'sudo greenprompt stop'"
            )
            sys.exit(1)
        port = args.port
        print(f"Stopping API server on port {port}...")
        try:
            result = subprocess.run(
                ["lsof", "-i", f":{port}"], capture_output=True, text=True
            )
            if result.stdout:
                pid = result.stdout.splitlines()[1].split()[1]
                subprocess.run(["kill", "-9", pid], check=True)
                print(f"Process on port {port} (PID {pid}) has been killed.")
            else:
                print(f"No process found listening on port {port}.")
        except Exception as e:
            print(f"Error stopping API server on port {port}: {e}")


if __name__ == "__main__":
    main()
