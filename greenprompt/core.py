"""
core.py — Prompt execution and energy calculation.

Orchestrates the full lifecycle of a single LLM prompt: power baseline
capture, Ollama HTTP call, post-call power measurement, prompt scoring,
and database persistence. This module is the primary integration point
between all other GreenPrompt subsystems.
"""

import requests
import time
import os
import tiktoken
from greenprompt import constants
from greenprompt.sysUsage import (
    get_system_info,
    measure_power_for_pid,
    has_gpu,
    get_gpu_usage,
)
from greenprompt.dbconn import save_prompt_usage
from greenprompt.scoreBasic import score_prompt

OLLAMA_URL = constants.OLLAMA_URL + "/api/generate"


#: Rough estimated energy per 1000 tokens, in watt-hours, keyed by model family.
#: These are order-of-magnitude heuristics for offline comparison, not
#: measurements — the hardware-measured `energy_wh` is the authoritative figure.
#: Add or calibrate entries here; see docs/configuration.md.
MODEL_ENERGY_MAP = {
    "gpt-3.5": 0.02,
    "gpt-4": 0.06,
    "gpt-4o": 0.04,
    "llama2": 0.01,
    "llama3": 0.012,
    "mistral": 0.008,
    "phi": 0.005,
}

#: Used when the model matches no entry above.
DEFAULT_ENERGY_PER_1K_WH = 0.01


def normalize_model_name(model):
    """
    Reduce an Ollama model reference to its bare family name.

    Ollama names carry a tag — "llama3.2:latest", "mistral:7b-instruct" — and
    may be namespaced ("library/llama3"). Lookups against MODEL_ENERGY_MAP are
    done on the bare, lowercased name so that a tag does not defeat the match.

    Args:
        model: A model reference, possibly tagged and/or namespaced.

    Returns:
        The lowercased family name, e.g. "llama3.2" for "library/llama3.2:latest".
        Returns "" for None or a blank string.
    """
    if not model:
        return ""
    name = str(model).split(":", 1)[0]  # drop the ":tag"
    name = name.rsplit("/", 1)[-1]  # drop any "namespace/"
    return name.strip().lower()


def estimate_energy_from_tokens(model, token_count):
    """
    Estimate energy usage (in watt-hours, Wh) from the model and token count.

    The model name is normalised first, then matched against MODEL_ENERGY_MAP:
    an exact family match wins, otherwise the longest matching prefix is used
    so that point releases inherit their family's rate ("llama3.2" -> "llama3").
    Anything unrecognised falls back to DEFAULT_ENERGY_PER_1K_WH.

    Matching on the raw name used to be an exact lookup, which no tagged Ollama
    model could ever satisfy — every prompt silently used the default rate.

    Parameters:
        model (str): Model reference, e.g. 'llama3.2:latest' or 'gpt-4o'.
        token_count (int): Total tokens for the prompt + response.

    Returns:
        float: Estimated energy consumption in Wh.
    """
    key = normalize_model_name(model)
    multiplier = MODEL_ENERGY_MAP.get(key)

    if multiplier is None:
        # Longest prefix first, so "gpt-4o" is preferred over "gpt-4".
        for family in sorted(MODEL_ENERGY_MAP, key=len, reverse=True):
            if key.startswith(family):
                multiplier = MODEL_ENERGY_MAP[family]
                break

    if multiplier is None:
        multiplier = DEFAULT_ENERGY_PER_1K_WH

    return (token_count / 1000) * multiplier


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
    """
    Execute a prompt through Ollama and measure its energy consumption.

    Sends the prompt to the local Ollama server, samples CPU/GPU power via
    the provided PowerMonitor (macOS) or falls back to zero values, scores
    the prompt with scoreBasic, and saves everything to SQLite.

    Args:
        prompt: The user's input text.
        model: Ollama model name (default "llama2"). Must be installed locally.
        monitor: A PowerMonitor instance (samplerMac.PowerMonitor) with an
            active sample buffer, or False/None to skip hardware measurement.

    Returns:
        dict with keys: prompt, prompt_score, prompt_score_details, response,
        model, prompt_tokens, completion_tokens, total_tokens,
        "total_energy (Wh)", duration_sec, "combined_power_w (W)",
        "cpu_power_w (W)", "gpu_power_w (W)", energy_estimate_tokens,
        energy_estimate_prompt, "baseline_energy (Wh)", "baseline_power (W)",
        gpu_usage, system_info.

    Raises:
        RuntimeError: If Ollama is unreachable or returns a non-200 response.
    """
    # Measure power usage before running the prompt
    current_pid = os.getpid()
    print(f"Current PID: {current_pid}")

    # Check for GPU and its usage
    gpu_usage = "No GPU detected"
    if has_gpu():
        print("GPU detected.")
        gpu_usage = get_gpu_usage()
        print("GPU Usage: " + str(gpu_usage))
    else:
        print("No GPU detected.")

    # Run the prompt
    start_time = time.time()
    end_time = None
    try:
        response = requests.post(
            OLLAMA_URL, json={"model": model, "prompt": prompt, "stream": False}
        )
        end_time = time.time()
        # Measure power usage after running the prompt
        duration = end_time - start_time
    except requests.exceptions.ConnectionError:
        raise RuntimeError("❌ Could not connect to Ollama at http://127.0.0.1:11434")

    if response.status_code != 200:
        raise RuntimeError(f"❌ Ollama error: {response.status_code} – {response.text}")

    # Measure power usage after running the prompt
    power_usage = measure_power_for_pid(current_pid, start_time, end_time, monitor)

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

    # Scored once and reused: score_prompt() runs the whole NLTK pipeline, and
    # this used to call it twice to fill in two adjacent fields.
    score = score_prompt(prompt)

    response = {
        "prompt": prompt,
        "prompt_score": score.get("score_percent", 0),
        "prompt_score_details": score.get("details", {}),
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
        "system_info": get_system_info(),
    }

    try:
        save_prompt_usage(response)
    except Exception as e:
        print(f"Warning: Failed to save prompt usage: {e}")

    return response
