# GreenPrompt REST API Reference

The GreenPrompt API server is a Flask application started with `sudo greenprompt run`. All endpoints are served on `http://localhost:<port>` (default port 5000).

---

## Base URL

```
http://localhost:5000
```

---

## Endpoints

### POST `/api/prompt`

Execute a prompt through Ollama, measure energy consumption, score the prompt, and persist the result.

**Request**

```
Content-Type: application/json
```

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `prompt` | string | Yes | — | The prompt text to send to the model |
| `model` | string | No | `"llama2"` | Ollama model name |

**Example request:**

```bash
curl -X POST http://localhost:5000/api/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "List 3 uses of solar energy. Format: bullets.", "model": "llama2"}'
```

**Response** `200 OK`

```json
{
  "prompt": "List 3 uses of solar energy. Format: bullets.",
  "prompt_score": 52.0,
  "prompt_score_details": {
    "RTCF Structure": 2,
    "Clarity & Specificity": 5,
    "Conciseness": 5,
    "Contextual Priming": 0,
    "Output Specification": 5,
    "Instructional Tone": 3,
    "Examples & Few-Shot": 0,
    "Task Decomposition": 0,
    "Positive/Negative Examples": 0,
    "Iterative Refinement": 0,
    "Creativity Control": 0,
    "Tone & Style": 0,
    "Error Prevention": 0,
    "Evaluation & Validation": 0,
    "Sensitivity & Inclusivity": 0,
    "Efficiency & Sustainability": 0,
    "Energy Awareness": 0,
    "Keyword Richness": 2
  },
  "response": "• Solar panels on homes generate electricity...",
  "model": "llama2",
  "prompt_tokens": 14,
  "completion_tokens": 63,
  "total_tokens": 77,
  "total_energy (Wh)": 0.000512,
  "duration_sec": 3.84,
  "combined_power_w (W)": 0.480,
  "cpu_power_w (W)": 0.348,
  "gpu_power_w (W)": 0.132,
  "energy_estimate_tokens": 0.00077,
  "energy_estimate_prompt": 0.00014,
  "baseline_energy (Wh)": 0.000067,
  "baseline_power (W)": 4.03,
  "gpu_usage": "No GPU detected",
  "system_info": {
    "OS": "Darwin",
    "OS Version": "...",
    "CPU": "Apple M2",
    "CPU Cores (Physical)": 8,
    "CPU Cores (Total)": 8,
    "RAM (Total)": "16.0 GB"
  }
}
```

**Error responses:**

| Status | Body | Cause |
|---|---|---|
| `400` | `{"error": "Prompt is required"}` | `prompt` field missing or empty |
| `500` | Flask traceback | Ollama not running or internal error |

---

### GET `/api/usage/all`

Retrieve all prompt usage records from the database, ordered by timestamp ascending.

**Example request:**

```bash
curl http://localhost:5000/api/usage/all
```

**Response** `200 OK` — JSON array of usage records:

```json
[
  {
    "id": 1,
    "timestamp": "2024-06-01T12:34:56.789012",
    "prompt": "Explain quantum computing.",
    "prompt_score": 28,
    "prompt_score_details": "{\"RTCF Structure\": 1, ...}",
    "response": "Quantum computing uses qubits...",
    "model": "llama2",
    "prompt_tokens": 5,
    "completion_tokens": 112,
    "total_tokens": 117,
    "energy_estimate_prompt": 0.00005,
    "energy_estimate_tokens": 0.00117,
    "duration_sec": 6.21,
    "energy_wh": 0.000891,
    "baseline_power_w": 4.1,
    "baseline_energy_wh": 0.000068,
    "cpu_power_w": 9.2,
    "gpu_power_w": 0.0,
    "combined_power_w": 9.2,
    "system_info": "{\"OS\": \"Darwin\", ...}"
  }
]
```

> **Note:** `prompt_score_details` and `system_info` are stored as JSON strings; parse with `JSON.parse()` in JavaScript or `json.loads()` in Python.

---

### GET `/api/usage/model/<model>`

Retrieve usage records filtered by model name.

**Path parameter:**

| Parameter | Description |
|---|---|
| `model` | Exact model name (case-sensitive, e.g., `llama2`, `mistral`) |

**Example request:**

```bash
curl http://localhost:5000/api/usage/model/llama2
```

**Response** `200 OK` — Same format as `/api/usage/all`, filtered to the specified model.

---

### GET `/api/usage/timeframe`

Retrieve usage records within a timestamp range.

**Query parameters:**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `start` | ISO 8601 string | Yes | Start of range (inclusive) |
| `end` | ISO 8601 string | Yes | End of range (inclusive) |

**Example request:**

```bash
curl "http://localhost:5000/api/usage/timeframe?start=2024-06-01T00:00:00&end=2024-06-30T23:59:59"
```

**Response** `200 OK` — Filtered usage records.

**Error response:**

| Status | Body | Cause |
|---|---|---|
| `400` | `{"error": "start and end query parameters are required"}` | Either parameter missing |

---

### GET `/dashboard`

Serves the Plotly analytics dashboard as an HTML page.

Open in a browser at `http://localhost:5000/dashboard` or launch via `greenprompt dashboard`.

**Response** `200 OK` — HTML page with embedded Plotly charts.

---

### `ANY /ollama/api/<path>`

Transparent reverse proxy to the local Ollama server at `http://localhost:11434/api/<path>`.

Supports `GET`, `POST`, `PUT`, `DELETE`, `PATCH`, and `OPTIONS`. Preserves all headers (except `Host` and `Content-Length`), query parameters, request body, and cookies.

**Example — list available models:**

```bash
curl http://localhost:5000/ollama/api/tags
```

**Example — generate via proxy:**

```bash
curl -X POST http://localhost:5000/ollama/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model": "llama2", "prompt": "Hello", "stream": false}'
```

> **Note:** Proxy calls are not currently logged to the GreenPrompt database. Only calls to `POST /api/prompt` are measured and stored.

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:5000"

# Run a prompt
response = requests.post(
    f"{BASE_URL}/api/prompt",
    json={"prompt": "Summarize quantum physics in 2 sentences.", "model": "llama2"}
)
data = response.json()
print(f"Energy used: {data['total_energy (Wh)']:.6f} Wh")
print(f"Prompt score: {data['prompt_score']:.1f}/50")
print(data["response"])

# Fetch all usage
all_usage = requests.get(f"{BASE_URL}/api/usage/all").json()
print(f"Total runs logged: {len(all_usage)}")

# Filter by model
llama_usage = requests.get(f"{BASE_URL}/api/usage/model/llama2").json()
total_energy = sum(r["energy_wh"] for r in llama_usage)
print(f"Total energy for llama2: {total_energy:.4f} Wh")
```

---

## Error Handling

The API does not currently return structured error envelopes for all error paths. When Ollama is unreachable, `run_prompt()` raises `RuntimeError` which propagates as an unhandled 500. When the database write fails, the error is caught and logged as a warning, but the response is still returned successfully.

Future versions will standardize error responses to:

```json
{
  "error": "human-readable message",
  "code": "ERROR_CODE"
}
```

---

## CORS

Flask-CORS is enabled on all endpoints (`CORS(app)`), allowing cross-origin requests from any origin. This is intentional to support browser extensions and external dashboards in development.
