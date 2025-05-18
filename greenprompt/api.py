from flask import Flask, request, jsonify
from flask_cors import CORS
from greenprompt.core import run_prompt

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

@app.route('/api/prompt', methods=['POST'])
def handle_prompt():
    data = request.get_json()
    prompt = data.get('prompt', '')
    model = data.get('model', 'llama2')

    if not prompt:
        return jsonify({'error': 'Prompt is required'}), 400

    result = run_prompt(prompt, model)
    return jsonify(result)

if __name__ == '__main__':
    app.run(debug=True)
