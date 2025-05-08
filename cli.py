

import argparse
from core import run_prompt

def main():
    parser = argparse.ArgumentParser(description="GreenPrompt CLI - Prompt Tracker & Energy Estimator")
    parser.add_argument("prompt", type=str, help="The prompt to send to Ollama")
    parser.add_argument("--model", type=str, default="llama2", help="Model to use (default: llama2)")
    args = parser.parse_args()

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

    except Exception as e:
        print(str(e))

if __name__ == "__main__":
    main()