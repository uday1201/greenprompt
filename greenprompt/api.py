"""
api.py — GreenPrompt Flask API server.

Started as a background subprocess by `greenprompt run`. Owns the PowerMonitor
lifecycle on macOS. Exposes REST endpoints for prompt execution, usage queries,
and the analytics dashboard. Also provides a reverse proxy to the local Ollama
server.

Endpoints:
    POST /api/prompt          — run a prompt, measure energy, save to DB
    GET  /api/usage/all       — retrieve all usage records
    GET  /api/usage/model/<m> — filter usage by model
    GET  /api/usage/timeframe — filter usage by timestamp range
    GET  /dashboard           — serve the Plotly analytics dashboard
    ANY  /ollama/api/<path>   — transparent proxy to Ollama at :11434

Known issues:
    - Line 2 import should be `from greenprompt.analytics import ...`
    - Ollama proxy URL uses /ollama/api/ but Ollama base is /api/
"""

from flask import Flask, render_template, request, jsonify, Response
from greenprompt.analytics import (
    load_usage_data,
    total_prompts_energy_usage,
    energy_usage_timeline,
    cpu_gpu_usage_per_prompt,
    estimated_vs_actual_power,
    baseline_vs_total_usage,
    model_comparison,
)
from flask_cors import CORS
from greenprompt.core import run_prompt
from greenprompt import constants
from greenprompt.dbconn import get_prompt_usage
import logging
import json
from plotly.utils import PlotlyJSONEncoder
import requests

# global variable to hold the power monitor instance
global monitor
monitor = None

LOG_FILE = "/tmp/api.log"
# Clear the log file at the start of the script
with open(LOG_FILE, "w"):
    pass

# Configure logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Add a StreamHandler for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logging.getLogger().addHandler(console_handler)


@app.route("/api/prompt", methods=["POST"])
def handle_prompt():
    """Run a prompt through core.run_prompt() and return energy/token metrics."""
    data = request.get_json(silent=True) or {}
    prompt = data.get("prompt", "")
    model = data.get("model", "llama3.2:latest")
    logging.info(f"Received prompt: {prompt} for model: {model}")
    if not prompt:
        logging.error("Prompt is required but not provided.")
        return jsonify({"error": "Prompt is required"}), 400
    try:
        result = run_prompt(prompt, model, monitor=monitor)
    except RuntimeError as e:
        logging.error(f"run_prompt failed: {e}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logging.error(f"Unexpected error in run_prompt: {e}")
        return jsonify({"error": "Internal server error", "detail": str(e)}), 500
    return jsonify(result)


@app.route("/api/usage/all", methods=["GET"])
def usage_all():
    """Return all prompt_usage records as a JSON array."""
    data = get_prompt_usage()
    return jsonify(data)


@app.route("/api/usage/model/<model>", methods=["GET"])
def usage_by_model(model):
    """Return usage records filtered by exact model name."""
    data = get_prompt_usage(model=model)
    return jsonify(data)


@app.route("/api/usage/timeframe", methods=["GET"])
def usage_by_timeframe():
    """Return usage records within a start/end ISO timestamp range (query params)."""
    start = request.args.get("start")
    end = request.args.get("end")
    if not start or not end:
        return jsonify({"error": "start and end query parameters are required"}), 400
    data = get_prompt_usage(start_time=start, end_time=end)
    return jsonify(data)


@app.route("/dashboard")
def dashboard():
    """Render the Plotly analytics dashboard as an HTML page."""
    df = load_usage_data()

    print(f"Loaded {len(df)} records from the database")

    total_prompts_energy = json.dumps(
        total_prompts_energy_usage(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    energy_usage = json.dumps(
        energy_usage_timeline(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    cpu_gpu_usage = json.dumps(
        cpu_gpu_usage_per_prompt(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    estimated_vs_actual = json.dumps(
        estimated_vs_actual_power(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    baseline_vs_total = json.dumps(
        baseline_vs_total_usage(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    model_comparison_chart = json.dumps(
        model_comparison(df).to_plotly_json(), cls=PlotlyJSONEncoder
    )
    logging.info("Dashboard data prepared successfully")

    return render_template(
        "dashboard.html",
        total_prompts_energy=total_prompts_energy,
        energy_usage=energy_usage,
        cpu_gpu_usage=cpu_gpu_usage,
        estimated_vs_actual=estimated_vs_actual,
        baseline_vs_total=baseline_vs_total,
        model_comparison=model_comparison_chart,
    )


@app.route(
    "/ollama/api/<path:subpath>",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
)
def ollama_proxy(subpath):
    """
    Proxy any Ollama API request to the local Ollama server at :11434.

    Note: the target URL path is currently /ollama/api/<subpath> which is
    incorrect — Ollama's base path is /api/<subpath>. This is a known bug.
    """
    # Construct the target URL on the Ollama server (default port 11434)
    target_url = f"http://localhost:11434/api/{subpath}"
    # Forward headers, preserving content type and authorization
    headers = {
        key: value
        for key, value in request.headers
        if key not in ["Host", "Content-Length"]
    }
    # Forward the request
    resp = requests.request(
        method=request.method,
        url=target_url,
        headers=headers,
        params=request.args,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        stream=True,
    )
    # Build a Flask Response
    excluded_headers = [
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    ]
    response_headers = [
        (name, value)
        for name, value in resp.raw.headers.items()
        if name.lower() not in excluded_headers
    ]
    return Response(resp.content, status=resp.status_code, headers=response_headers)


if __name__ == "__main__":
    import argparse as _argparse
    _parser = _argparse.ArgumentParser()
    _parser.add_argument("--port", type=int, default=5000)
    _args = _parser.parse_args()

    if constants.OS == "Darwin":
        from greenprompt.samplerMac import PowerMonitor
        monitor = PowerMonitor()
        monitor.start()
    elif constants.OS == "Linux":
        from greenprompt.samplerLinux import LinuxPowerMonitor
        monitor = LinuxPowerMonitor(cpu_tdp_w=getattr(constants, "CPU_TDP_W", 40.0))
        monitor.start()
    logging.info("Starting API server...")
    app.run(host="127.0.0.1", port=_args.port, debug=False)
