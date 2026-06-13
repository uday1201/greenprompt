Score and improve a prompt using GreenPrompt's 18-dimension scoring system.

The scorer is in `greenprompt/scoreBasic.py`. It uses NLTK POS tagging and regex heuristics — no model call needed.

The prompt to score: $ARGUMENTS

Steps:
1. If no prompt is provided in $ARGUMENTS, ask the user to provide one.
2. Score the prompt by running:
   ```bash
   cd /path/to/greenprompt && python -c "
   from greenprompt.scoreBasic import score_prompt
   import json
   result = score_prompt('''PROMPT_HERE''')
   print(json.dumps(result, indent=2))
   "
   ```
   If the package isn't importable from the current directory, try `pip show greenprompt` to find the install path.
3. Display the results as a table:
   - Each dimension, its score, and its maximum
   - Total score and percentage
   - A ✅ for full score, ⚠️ for partial, ❌ for zero
4. Identify the top 3 dimensions with the most room for improvement (zero or partial scores that are achievable).
5. Rewrite the prompt with targeted improvements to those 3 dimensions. Show the rewritten version clearly.
6. Score the improved prompt using the same method and show the before/after comparison.
7. Explain what changed and why each change improves the score.

Key scoring dimensions reference:
- RTCF (4pts): Role ("You are a..."), Task (action verb), Context ("Context: ..."), Format ("Format: bullets")
- Conciseness (5pts): loses 1pt per filler phrase ("please", "could you", "just", "I would like you to")
- Output Specification (5pts): "Format: JSON", "output as a table", "provide as CSV"
- Clarity (5pts): action verb + prompt ≤400 chars
- Error Prevention (2pts): "if unsure, say so", "do not guess"
- Energy Awareness (2pts): "concise", "minimize tokens", "green", "efficient"
