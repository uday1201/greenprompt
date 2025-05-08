import requests
import datetime
import os

# Replace with your OpenAI API key or read from env variable
API_KEY = "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"

# Headers for OpenAI API
headers = {
    "Authorization": f"Bearer {API_KEY}",
}

# Sample OpenAI model call to get token usage

def run_sample_prompt():
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "How much energy does an AI model like ChatGPT consume per prompt?"}
        ],
        "temperature": 0.7
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        data = response.json()
        usage = data.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        print(f"\n🧾 Token Usage:")
        print(f"Prompt tokens: {prompt_tokens}")
        print(f"Completion tokens: {completion_tokens}")
        print(f"Total tokens: {total_tokens}")
    else:
        print(f"\n❌ Failed to complete prompt: {response.status_code} – {response.text}")

if __name__ == "__main__":
    print("🚀 Running test prompt to measure token usage...")
    run_sample_prompt()
