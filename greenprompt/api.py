from flask import Flask, request, jsonify
from flask_cors import CORS
from greenprompt.core import run_prompt
from . import constants
from greenprompt.dbconn import get_prompt_usage
import logging
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

if __name__ == '__main__':
    logging.info("Starting API server...")
    app.run(debug=False)
