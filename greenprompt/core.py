import requests
import time
import psutil
import os
import tiktoken  # Ensure this library is installed: pip install tiktoken
from .sysUsage import get_system_info, measure_power_for_pid, has_gpu, get_gpu_usage

OLLAMA_URL = "http://localhost:11434/api/generate"

def estimate_energy_from_tokens(model, token_count):
    """
    Estimate energy usage (in watt-hours, Wh) based on the model type and token count.

    Parameters:
        model (str): The name of the model used (e.g., 'gpt-3.5', 'llama2').
        token_count (int): The total number of tokens used for the prompt + response.

    Returns:
        float: Estimated energy consumption in Wh.
    """
    # Mapping model to estimated energy usage per 1000 tokens (Wh)
    MODEL_ENERGY_MAP = {
        "gpt-3.5": 0.02,
        "gpt-4": 0.06,
        "gpt-4o": 0.04,
        "llama2": 0.01,
        "mistral": 0.008,
        "phi": 0.005,
    }

    model_key = model.lower()
    multiplier = MODEL_ENERGY_MAP.get(model_key, 0.01)  # Default fallback if unknown
    energy = (token_count / 1000) * multiplier
    return energy

def estimate_tokens_from_prompt(prompt, model="gpt-3.5"):
    """
    Estimate how many tokens a prompt would use in a given model.

    Parameters:
        prompt (str): The natural language input.
        model (str): The model name for token encoding logic (default = 'gpt-3.5').

    Returns:
        int: Estimated number of tokens.
    """
    try:
        # Try to use the model-specific encoding
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to general-purpose encoding
        enc = tiktoken.get_encoding("cl100k_base")

    tokens = enc.encode(prompt)
    return len(tokens)

def get_cpu_power_estimate():
    cpu_percent = psutil.cpu_percent(interval=1)
    estimated_power = (cpu_percent / 100.0) * 15  # Assume 15W CPU
    return estimated_power

def estimate_energy(cpu_before, cpu_after, duration_sec):
    avg_power = (cpu_before + cpu_after) / 2
    return (avg_power * duration_sec) / 3600  # Convert to Wh

def run_prompt(prompt, model="llama2"):
    # Get system information
    system_info = get_system_info()
    print("System Information:")
    for key, value in system_info.items():
        print(f"{key}: {value}")

    # Measure power usage before running the prompt
    current_pid = os.getpid()
    power_usage_before = measure_power_for_pid(current_pid, duration=1)

    # Check for GPU and its usage
    if has_gpu():
        print("\nGPU detected.")
        gpu_usage = get_gpu_usage()
        print("GPU Usage:")
        print(gpu_usage)
    else:
        print("\nNo GPU detected.")

    # Run the prompt
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

    # Measure power usage after running the prompt
    power_usage_after = measure_power_for_pid(current_pid, duration=1)

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
        "energy_wh": energy_wh,
        "power_usage_before": power_usage_before,
        "power_usage_after": power_usage_after,
        "gpu_usage": gpu_usage if has_gpu() else "No GPU detected",
        "system_info": system_info
    }