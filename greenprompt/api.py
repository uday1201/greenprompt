from flask import Flask, request, jsonify
from flask_cors import CORS
from greenprompt.core import run_prompt
import constants
from samplerMac import PowerMonitor
from greenprompt.dbconn import get_prompt_usage

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

if constants.OS == "Darwin":
    # Initialize the power monitor for macOS
    monitor = PowerMonitor()
    monitor.start()
    print("Power monitor started.")

@app.route('/api/prompt', methods=['POST'])
def handle_prompt():
    data = request.get_json()
    prompt = data.get('prompt', '')
    model = data.get('model', 'llama2')

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400
    if constants.OS == "Darwin":
        result = run_prompt(prompt, model, monitor=monitor)
    return jsonify(result)

@app.route('/api/usage/all', methods=['GET'])
def usage_all():
    data = get_prompt_usage()
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
    app.run(debug=True)
