from flask import Flask, request, render_template
from core import run_prompt

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        prompt = request.form["prompt"]
        model = request.form.get("model", "llama2")
        try:
            result = run_prompt(prompt, model=model)
        except Exception as e:
            result = {"error": str(e)}
    return render_template("index.html", result=result)

def run_app():
    print("🌱 Starting GreenPrompt at http://localhost:5000 ...")
    app.run(port=5000, debug=True)

if __name__ == "__main__":
    run_app()
