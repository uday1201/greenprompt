from flask import Flask, render_template, request, jsonify, Response
from analytics import (
    load_usage_data, 
    total_prompts_energy_usage,
    energy_usage_timeline,
    cpu_gpu_usage_per_prompt,
    estimated_vs_actual_power,
    baseline_vs_total_usage,
    model_comparison
)
from flask_cors import CORS
from greenprompt.core import run_prompt
from greenprompt import constants
from greenprompt.dbconn import get_prompt_usage
import logging
import json
from plotly.utils import PlotlyJSONEncoder
import requests

if constants.OS == "Darwin":
    from greenprompt.setup import monitor

# Clear the log file at the start of the script
with open('./api.log', 'w'):
    pass

# Configure logging
logging.basicConfig(
    filename='./api.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Add a StreamHandler for debugging
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

@app.route('/api/prompt', methods=['POST'])
def handle_prompt():
    data = request.get_json()
    prompt = data.get('prompt', '')
    model = data.get('model', 'llama2')
    logging.info(f"Received prompt: {prompt} for model: {model}")
    if not prompt:
        logging.error("Prompt is required but not provided.")
        return jsonify({'error': 'Prompt is required'}), 400
    if constants.OS == "Darwin":
        result = run_prompt(prompt, model, monitor=monitor)
    else:
        result = run_prompt(prompt, model, False)
    logging.info(f"Prompt handled successfully")
    return jsonify(result)

@app.route('/api/usage/all', methods=['GET'])
def usage_all():
    data = get_prompt_usage()
    logging.info(f"Fetched all usage data")
    return jsonify(data)

@app.route('/api/usage/model/<model>', methods=['GET'])
def usage_by_model(model):
    data = get_prompt_usage(model=model)
    return jsonify(data)

@app.route('/api/usage/timeframe', methods=['GET'])
def usage_by_timeframe():
    start = request.args.get('start')
    end = request.args.get('end')
    if not start or not end:
        return jsonify({'error': 'start and end query parameters are required'}), 400
    data = get_prompt_usage(start_time=start, end_time=end)
    return jsonify(data)

@app.route("/dashboard")
def dashboard():
    df = load_usage_data()

    print(f"Loaded {len(df)} records from the database")

    total_prompts_energy = json.dumps(total_prompts_energy_usage(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    energy_usage = json.dumps(energy_usage_timeline(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    cpu_gpu_usage = json.dumps(cpu_gpu_usage_per_prompt(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    estimated_vs_actual = json.dumps(estimated_vs_actual_power(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    baseline_vs_total = json.dumps(baseline_vs_total_usage(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    model_comparison_chart = json.dumps(model_comparison(df).to_plotly_json(), cls=PlotlyJSONEncoder)
    logging.info("Dashboard data prepared successfully")

    return render_template(
        "dashboard.html",
        total_prompts_energy=total_prompts_energy,
        energy_usage=energy_usage,
        cpu_gpu_usage=cpu_gpu_usage,
        estimated_vs_actual=estimated_vs_actual,
        baseline_vs_total=baseline_vs_total,
        model_comparison=model_comparison_chart
    )

@app.route('/ollama/api/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'])
def ollama_proxy(subpath):
    """
    Proxy any Ollama API request (under /ollama/api/) to the local Ollama server.
    """
    # Construct the target URL on the Ollama server (default port 11434)
    target_url = f"http://localhost:11434/ollama/api/{subpath}"
    # Forward headers, preserving content type and authorization
    headers = {key: value for key, value in request.headers if key not in ['Host', 'Content-Length']}
    # Forward the request
    resp = requests.request(
        method=request.method,
        url=target_url,
        headers=headers,
        params=request.args,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False,
        stream=True
    )
    # Build a Flask Response
    excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
    response_headers = [(name, value) for name, value in resp.raw.headers.items() if name.lower() not in excluded_headers]
    return Response(resp.content, status=resp.status_code, headers=response_headers)

if __name__ == '__main__':
    logging.info("Starting API server...")
    app.run(debug=False)
