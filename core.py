import requests
import time
import psutil

OLLAMA_URL = "http://localhost:11434/api/generate"

def get_cpu_power_estimate():
    cpu_percent = psutil.cpu_percent(interval=1)
    estimated_power = (cpu_percent / 100.0) * 15  # Assume 15W CPU
    return estimated_power

def estimate_energy(cpu_before, cpu_after, duration_sec):
    avg_power = (cpu_before + cpu_after) / 2
    return (avg_power * duration_sec) / 3600  # Convert to Wh

def run_prompt(prompt, model="llama2"):
    cpu_before = get_cpu_power_estimate()
    start_time = time.time()

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False
        })
        duration = time.time() - start_time
        cpu_after = get_cpu_power_estimate()
    except requests.exceptions.ConnectionError:
        raise RuntimeError("❌ Could not connect to Ollama at http://localhost:11434")

    if response.status_code != 200:
        raise RuntimeError(f"❌ Ollama error: {response.status_code} – {response.text}")

    data = response.json()
    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    total_tokens = prompt_tokens + completion_tokens
    energy_wh = estimate_energy(cpu_before, cpu_after, duration)

    return {
        "response": data.get("response", ""),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "duration_sec": duration,
        "energy_wh": energy_wh
    }