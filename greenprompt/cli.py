import argparse
import os
from pprint import pprint
import shutil
import sys
import subprocess
from greenprompt.dbconn import get_prompt_usage, init_db
from greenprompt.setup import main as setup_main, monitor
from greenprompt.core import run_prompt
from greenprompt.sysUsage import get_system_info
    
def run_api(port):
    """
    Run the API server on the specified port.
    """
    print(f"Starting API server on port {port}...")

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
    subprocess.Popen(
        ["sudo", "poetry", "run", "python", "api.py", f"--port={port}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"API server is running on port {port} in the background.")

def display_monitor(start_time=None, end_time=None, model=None):
    """
    Display the last 10 usage rows like a monitoring tool.
    """
    print("Fetching the last 10 usage rows...")
    rows = get_prompt_usage(start_time=None, end_time=None, model=None)
    for row in rows[-10:]:
        pprint(row)

def log_api():
    """
    Tail the logs of the API process.
    """
    print("Tailing the API logs...")
    try:
        subprocess.run(["sudo", "tail", "-f", "api.log"], check=True)
    except KeyboardInterrupt:
        print("\nStopped tailing the API logs.")

def main():
    parser = argparse.ArgumentParser(
        prog='greenprompt',
        description='GreenPrompt CLI: track energy usage of LLM prompts on macOS'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # setup command
    p_setup = subparsers.add_parser('setup', help='Install and configure Ollama, initialize database, generate constants')
    # run command
    p_run = subparsers.add_parser('run', help='Start the web API server and dashboard')
    p_run.add_argument('--port', type=int, default=5000, help='Port for the web server (default: 5000)')
    # prompt command
    p_prompt = subparsers.add_parser('prompt', help='Send a prompt and display energy/token stats')
    p_prompt.add_argument('prompt', type=str, help='The prompt text to send')
    p_prompt.add_argument('--model', type=str, default='llama2', help='Model to use (default: llama2)')
    # monitor command
    p_mon = subparsers.add_parser('monitor', help='Display the last N prompt usage entries')
    p_mon.add_argument('--count', type=int, default=10, help='Number of entries to show (default: 10)')
    # log_api command (optional)
    p_log = subparsers.add_parser('log_api', help='Tail the API server logs')

    args = parser.parse_args()

    if args.command == 'setup':
        # 1) check/install Ollama
        if not shutil.which("ollama"):
            print("Installing Ollama via Homebrew...")
            subprocess.run(["brew", "install", "ollama"], check=True)
        # 2) initialize DB
        print("Initializing database...")
        init_db()
        # 3) generate constants.py
        print("Generating constants.py...")
        system_info = get_system_info()
        constants_path = os.path.join(os.getcwd(), "constants.py")
        with open(constants_path, "w") as f:
            f.write("# Auto-generated constants file\n")
            for k, v in system_info.items():
                key = k.upper().replace(" ", "_").replace("(", "").replace(")", "")
                f.write(f"{key} = {repr(v)}\n")
        print(f"✅ Setup complete: database initialized and constants saved to {constants_path}")

    elif args.command == 'run':
        print(f"Starting API server on port {args.port}...")
        run_api(port=args.port)

    elif args.command == 'prompt':
        result = run_prompt(args.prompt, model=args.model)
        print("\nResponse:\n" + result.get("response", ""))
        print("\n--- Prompt usage data ---")
        print(f"Prompt tokens: {result.get('prompt_tokens')}")
        print(f"Completion tokens: {result.get('completion_tokens')}")
        print(f"Total tokens: {result.get('total_tokens')}")
        print(f"Duration (sec): {result.get('duration_sec')}")
        print(f"Baseline power (W): {result.get('baseline_power_w')}")
        print(f"Baseline energy (Wh): {result.get('baseline_energy_wh')}")
        print(f"CPU power (W): {result.get('cpu_power_w')}")
        print(f"GPU power (W): {result.get('gpu_power_w')}")
        print(f"Combined power (W): {result.get('combined_power_w')}")
        print(f"Energy used (Wh): {result.get('energy_wh')}")

    elif args.command == 'monitor':
        entries = get_prompt_usage(start_time=None, end_time=None, model=None)
        for entry in entries[-args.count:]:
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

    elif args.command == 'log_api':
        print("Tailing the API logs...")
        try:
            subprocess.run(["sudo", "tail", "-f", "api.log"], check=True)
        except KeyboardInterrupt:
            print("\nStopped tailing the API logs.")

if __name__ == "__main__":
    main()