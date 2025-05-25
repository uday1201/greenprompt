import requests
import time
import psutil
import os
import tiktoken
from greenprompt import constants
from greenprompt.sysUsage import get_system_info, measure_power_for_pid, has_gpu, get_gpu_usage
from greenprompt.dbconn import save_prompt_usage

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

def run_prompt(prompt, model="llama2", monitor=False):

    # Measure power usage before running the prompt
    current_pid = os.getpid()
    print(f"Current PID: {current_pid}")

    # Check for GPU and its usage
    if has_gpu():
        print("GPU detected.")
        gpu_usage = get_gpu_usage()
        print("GPU Usage: " + gpu_usage)
    else:
        print("No GPU detected.")

    # Run the prompt
    start_time = time.time()
    end_time = None
    try:
        response = requests.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False
        })
        end_time = time.time()
        # Measure power usage after running the prompt
        duration = end_time - start_time
    except requests.exceptions.ConnectionError:
        raise RuntimeError("❌ Could not connect to Ollama at http://localhost:11434")

    if response.status_code != 200:
        raise RuntimeError(f"❌ Ollama error: {response.status_code} – {response.text}")

    # Measure power usage after running the prompt
    power_usage = measure_power_for_pid(current_pid, start_time, end_time, monitor)
    print(power_usage)

    data = response.json()
    prompt_tokens = data.get("prompt_eval_count", 0)
    completion_tokens = data.get("eval_count", 0)
    total_tokens = prompt_tokens + completion_tokens
    # Check if power usage data is complete
    if power_usage and isinstance(power_usage, dict) and "energy_wh" in power_usage:
        total_energy = power_usage.get("energy_wh", 0)
        combined_power_w = power_usage.get("combined_power_w", 0)
        cpu_power = power_usage.get("cpu_power_w", 0)
        gpu_power = power_usage.get("gpu_power_w", 0)
        baseline_energy = power_usage.get("baseline_energy_wh", 0)
        baseline_power = power_usage.get("baseline_power_w", 0)
    else:
        total_energy = 0
        combined_power_w = 0
        cpu_power = 0
        gpu_power = 0
        baseline_energy = 0
        baseline_power = 0
        print("Warning: Power usage data is incomplete or missing.")

    energy_estimate_tokens = estimate_energy_from_tokens(model, total_tokens)
    energy_estimate_prompt = estimate_energy_from_tokens(model, prompt_tokens)

    response = {
        "prompt": prompt,
        "response": data.get("response", ""),
        "model": model,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "total_energy (Wh)": total_energy,
        "duration_sec": duration,
        "combined_power_w (W)": combined_power_w,
        "cpu_power_w (W)": cpu_power,
        "gpu_power_w (W)": gpu_power,
        "energy_estimate_tokens": energy_estimate_tokens,
        "energy_estimate_prompt": energy_estimate_prompt,
        "baseline_energy (Wh)": baseline_energy,
        "baseline_power (W)": baseline_power,
        "gpu_usage": gpu_usage if has_gpu() else "No GPU detected",
        "system_info": get_system_info()
    }
    
    try:
        save_prompt_usage(response)
    except Exception as e:
        print(f"Warning: Failed to save prompt usage: {e}")

    return response