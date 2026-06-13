# GreenPrompt Prompt Scoring

GreenPrompt automatically scores every prompt on 18 quality dimensions. You can also score prompts standalone:

```bash
greenprompt score "Your prompt here"
```

Or via API (score is included in every `/api/prompt` response):

```json
{
  "prompt_score": 36.0,
  "prompt_score_details": { ... }
}
```

The scorer is entirely **offline** — it uses NLTK POS tagging and regex heuristics. No LLM call is made. Typical latency is under 50ms.

---

## Scoring Framework

Scores are based on the **RTCF framework** (Role, Task, Context, Format) extended with 14 additional prompt engineering dimensions from research literature.

**Maximum total score: 50 points**

Score percent = `(total / 50) × 100`

---

## Dimensions Reference

### 1. RTCF Structure (0–4 pts, 1 pt per element)

Checks for the four foundational prompt components.

| Element | Detection | Example trigger |
|---|---|---|
| **Role** | Regex: `you are (a/an/the)? <word>`, `pretend to be`, `act as`, `role:` | `"You are a physics expert."` |
| **Task** | POS tag: any imperative verb in the core verb list | `"Explain"`, `"Summarize"`, `"List"` |
| **Context** | Regex: `context:`, `background:`, `for <word>`, `audience:` | `"Context: audience is a beginner."` |
| **Format** | Regex: `format:`, `output as`, or content-type words | `"Format: bullet points."` |

**Core task verbs recognized:** `summarize`, `list`, `explain`, `describe`, `define`, `compare`, `generate`, `analyze`, `write`, `compose`, `translate`, `solve`, `classify`, `extract`, `categorize`, `review`, `evaluate`

---

### 2. Clarity & Specificity (0, 3, or 5 pts)

- **5 pts**: A task verb is present AND the prompt is ≤ 400 characters.
- **3 pts**: A task verb is present but the prompt exceeds 400 characters.
- **0 pts**: No task verb detected.

**Tip:** Keep prompts under 400 characters. If you need more context, use `context:` or `background:` markers to get Contextual Priming points separately.

---

### 3. Conciseness (0–5 pts)

Starts at 5 and deducts 1 point per detected filler phrase (minimum 0).

**Filler phrases that cost points:**
- `could you`, `please`, `would you mind`, `kindly`, `if possible`
- `try to`, `attempt to`, `please try`, `just`, `simply`
- `I would like you to`, `I want you to`, `can you`

**Example:**
- `"Could you please, if possible, just summarize this?"` → 3 fillers → 2 pts
- `"Summarize this article."` → 0 fillers → 5 pts

---

### 4. Contextual Priming (0 or 3 pts)

Detected by: `context:`, `background:`, `for <word>` pattern, or `audience:`

```
# Earns points:
"Context: I'm writing a technical blog post for developers."
"Audience: high school students."
"Background: this is for a legal document."
```

---

### 5. Output Specification (0 or 5 pts)

Detected by: `format:`, `output as`, or any of `table`, `bullets`, `list`, `json`, `csv`, `markdown` in proximity to `provide`.

```
# Earns points:
"Format: JSON."
"Output as a markdown table."
"Provide the answer as a CSV."
"List the results in bullet points."
```

---

### 6. Instructional Tone (0 or 3 pts)

Detected by NLTK POS tagging: any verb tagged as a verb (`VB`) in the prompt.

This captures imperative verbs (`List`, `Explain`, `Write`) as well as other action verbs.

---

### 7. Examples & Few-Shot Learning (0 or 2 pts)

Detected by: `example:`, `Q:`, `A:`, `sample output`, `for instance`, `e.g.`

```
# Earns points:
"Q: What is 2+2? A: 4. Q: What is 3+3?"
"For instance: 'The cat sat.' → sentiment: positive."
"Example: apple → fruit, hammer → tool."
```

---

### 8. Task Decomposition (0 or 2 pts)

Detected by: `first...then` sequence (across the prompt) or `step N` numbering.

```
# Earns points:
"First summarize the text, then translate it to French."
"Step 1: define the term. Step 2: give an example."
```

---

### 9. Positive and Negative Examples (0 or 2 pts)

Detected by: `do not`, `exclude`, `not include`, `except`

```
# Earns points:
"List fruits. Do not include vegetables."
"Generate names. Exclude any that start with 'J'."
```

---

### 10. Iterative Refinement (0 or 2 pts)

Detected by: `revise`, `improve`, `refine`, `rewrite`, `repeat`

```
# Earns points:
"Write a summary, then refine it to be more concise."
"Generate the answer and revise for accuracy."
```

---

### 11. Creativity Control (0 or 2 pts)

Detected by: `creative`, `imaginative`, `unusual`, `original`, `unique`, `be bold`, `inventive`

```
# Earns points:
"Give three creative uses for a paperclip."
"Write an imaginative story about the moon."
```

---

### 12. Tone & Style Consistency (0 or 2 pts)

Detected by: `tone:`, `style:`, `use a <adjective> tone`, `in a <adjective> style`, or explicit tone words: `formal`, `casual`, `friendly`, `professional`, `humorous`, `serious`

```
# Earns points:
"Tone: casual and friendly."
"Write in a formal academic style."
"Use a humorous tone."
```

---

### 13. Error Prevention (0 or 2 pts)

Detected by: `do not guess`, `only answer if sure`, `if unsure, say so`, `if you do not know`

```
# Earns points:
"Answer only if you are sure. If unsure, say so."
"Do not guess. Only provide verified facts."
```

---

### 14. Evaluation & Validation (0 or 2 pts)

Detected by: `double-check`, `verify`, `validate`, `ensure accuracy`, `cross-check`, `review your answer`

```
# Earns points:
"List 5 capitals and double-check each one."
"Verify your answer before responding."
```

---

### 15. Sensitivity & Inclusivity (0 or 2 pts)

Detected by: `inclusive`, `respectful`, `avoid bias`, `unbiased`, `sensitive to`

```
# Earns points:
"Describe this cultural practice. Be inclusive and respectful."
"Write an unbiased summary of both perspectives."
```

---

### 16. Efficiency & Sustainability (0 or 2 pts)

Detected by: `concise`, `briefly`, `short answer`, `max N words`, `minimize tokens`, `eco-friendly`, `efficient`

```
# Earns points:
"Briefly explain in under 50 words."
"Give a concise answer. Minimize tokens."
```

---

### 17. Energy Awareness (0 or 2 pts)

Detected by: `energy usage`, `carbon`, `footprint`, `sustainable`, `green`, `efficient`

This dimension specifically rewards prompts that are conscious of their computational footprint.

```
# Earns points:
"Provide a green, efficient response."
"Minimize the carbon footprint of this interaction."
```

---

### 18. Keyword Richness (0, 1, or 2 pts)

Counts unique non-stopword alphabetic tokens using NLTK's English stopword list.

- **2 pts**: 5 or more unique keywords
- **1 pt**: 2–4 unique keywords
- **0 pts**: fewer than 2 unique keywords

This rewards prompts that use specific, meaningful vocabulary.

---

## Scoring Example

Prompt:
```
You are a physics teacher. Explain Newton's second law of motion to a high school student.
Context: The student has basic algebra knowledge. Format: bullet points.
If unsure, say so. Double-check your answer.
```

| Dimension | Score | Reason |
|---|---|---|
| RTCF Structure | 4 | Role ✓, Task ✓, Context ✓, Format ✓ |
| Clarity & Specificity | 3 | Has task verb but prompt > 400 chars |
| Conciseness | 5 | No filler phrases |
| Contextual Priming | 3 | `Context:` present |
| Output Specification | 5 | `Format: bullet points` |
| Instructional Tone | 3 | "Explain" detected as verb |
| Examples & Few-Shot | 0 | No examples provided |
| Task Decomposition | 0 | No step sequence |
| Positive/Negative Examples | 0 | No exclusion rules |
| Iterative Refinement | 0 | No revision instruction |
| Creativity Control | 0 | No creativity instruction |
| Tone & Style | 0 | No tone specified |
| Error Prevention | 2 | "If unsure, say so" |
| Evaluation & Validation | 2 | "Double-check" |
| Sensitivity & Inclusivity | 0 | Not specified |
| Efficiency & Sustainability | 0 | Not specified |
| Energy Awareness | 0 | Not specified |
| Keyword Richness | 2 | Many unique keywords |
| **Total** | **32** | **64% (32/50)** |

---

## Optimizing for Score

To get a near-perfect score, combine all elements:

```
You are an expert data scientist. [Role]
Analyze the following sales data and identify the top 3 trends. [Task, Clarity]
Context: audience is a non-technical executive team. [Contextual Priming]
Format: a JSON object with keys "trend", "evidence", "recommendation". [Output Spec]
First identify outliers, then compute averages, then rank by impact. [Task Decomposition]
Include only statistically significant trends; exclude noise. [Positive/Negative]
Tone: professional and concise. [Tone & Style]
If unsure of any trend, say so. Double-check your calculations. [Error Prevention, Validation]
Respond briefly — minimize tokens and energy usage. [Efficiency, Energy Awareness]
For instance: {"trend": "Q3 spike", "evidence": "up 40%", "recommendation": "invest"} [Examples]
```

> **Note:** A high score does not guarantee a better LLM response — it indicates alignment with recognized prompt engineering best practices. The score is most useful as a consistent, fast signal for prompt quality comparison and optimization workflows.

---

## Limitations

- Role detection requires common English patterns (`you are`, `act as`, `role:`). Custom persona phrasing may not be detected.
- Task verb detection relies on NLTK POS tagging, which can misclassify rare verb forms.
- Regex patterns are English-only.
- The scorer does not evaluate semantic quality — a grammatically poor but structurally rich prompt may still score high.
- `score_prompt()` is called twice in `run_prompt()` (once for `prompt_score`, once for `prompt_score_details`). This is a known inefficiency.
