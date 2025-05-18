import argparse
import os
import subprocess
import sys
from datetime import datetime
from greenprompt.core import run_prompt

def setup_ollama_proxy():
    print("🔧 Setting up GreenPrompt proxy...")

    # Stop existing Ollama instance
    print("🛑 Attempting to stop any existing Ollama instance...")
    subprocess.run(["pkill", "-f", "ollama"], stderr=subprocess.DEVNULL)

    # Start Ollama on port 11435
    print("🚀 Starting Ollama on port 11435...")
    try:
        subprocess.Popen(["ollama", "serve"], env={**os.environ, "OLLAMA_PORT": "11435"})
        print("✅ Ollama now running on port 11435.")
    except FileNotFoundError:
        print("❌ Ollama is not installed or not in your PATH.")
        sys.exit(1)

    print("⚠️ Now run the GreenPrompt proxy on port 11434 to complete setup.")

def main():
    parser = argparse.ArgumentParser(description="GreenPrompt CLI - Prompt Tracker & Energy Estimator")
    parser.add_argument("prompt", nargs="?", type=str, help="The prompt to send to Ollama")
    parser.add_argument("--model", type=str, default="llama2", help="Model to use (default: llama2)")
    parser.add_argument("--log", action="store_true", default=True, help="Log prompt and stats to a local file")
    parser.add_argument("--setup", action="store_true", help="Rebind Ollama to port 11435 and prepare proxy port")
    args = parser.parse_args()

    if args.setup:
        setup_ollama_proxy()
        return

    if not args.prompt:
        print("❌ Please provide a prompt or use --setup.")
        return

    try:
        result = run_prompt(args.prompt, model=args.model)

        print("\n🧠 Response:")
        print(result["response"])
        print("\n📊 Stats:")
        print(f"Model: {result['model']}")
        print(f"Prompt tokens: {result['prompt_tokens']}")
        print(f"Completion tokens: {result['completion_tokens']}")
        print(f"Total tokens: {result['total_tokens']}")
        print(f"Duration: {result['duration_sec']:.2f} sec")
        print(f"Estimated Energy: {result['energy_wh']:.6f} Wh")

        if args.log:
            with open("greenprompt_logs.txt", "a") as log_file:
                log_file.write(f"{datetime.now()} | Model: {result['model']} | Prompt: {args.prompt}\n")
                log_file.write(f"Tokens: {result['total_tokens']} | Energy: {result['energy_wh']:.6f} Wh\n")
                log_file.write(f"Response: {result['response']}\n\n")

    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    main()