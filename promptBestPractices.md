# 📘 Comprehensive Prompt-Writing Best Practices

A clear, well-structured prompt dramatically improves the quality of AI-generated outputs. This guide outlines key principles and examples for writing effective prompts using the **RTCF** framework and other best practices.

---

## 🧱 1. Prompt Structure: **RTCF**

| Element | Description | Example |
|--------|-------------|---------|
| **R - Role** | Specify the model's persona or role | `You are an expert AI assistant specialized in physics.` |
| **T - Task** | Define the action you want | `Explain Newton’s second law of motion.` |
| **C - Context** | Provide relevant background | `Context: The audience has high school-level physics knowledge.` |
| **F - Format** | Specify output format | `Respond in concise bullet points.` |

---

## 🔍 2. Clarity & Specificity

- Be direct, avoid vague terms like *some*, *might*, *many*.
- ✅ `List three lesser-known facts about photosynthesis.`
- ❌ `Tell me something interesting about plants.`

---

## ✂️ 3. Conciseness

- Avoid filler phrases like “please”, “if you don’t mind”.
- ✅ `Summarize this article.`
- ❌ `Could you please, if possible, summarize this article for me?`

---

## 🧠 4. Contextual Priming

- Give necessary background up front.

```markdown
Context: I’m writing a blog post on AI ethics.  
Task: List five key ethical concerns related to AI.
```

---

## 🧾 5. Output Specification

- Define scope and format explicitly.
- ✅ `Write a 50-word summary of quantum computing. Format: Plain text.`
- ✅ `Give three reasons renewable energy matters. Format: Bullet points.`

---

## 📢 6. Instructional Tone

- Use verbs like: `Summarize`, `List`, `Explain`, `Compare`.
- ✅ `List 5 advantages of solar power.`
- ❌ `Could you maybe tell me about some advantages solar power might have?`

---

## 🎯 7. Examples and Few-Shot Learning

- Include clear examples of the desired style/format to guide the model.

---

## 🧩 8. Task Decomposition

- Break complex tasks into parts:

```markdown
Explain photosynthesis:  
1. Define it  
2. Describe the steps  
3. List three example plants
```

---

## ✅❌ 9. Positive and Negative Examples

- Clarify both what to include and exclude.
- Example:
  `Generate a list of fruits (e.g., apple, banana). Do NOT include vegetables or grains.`

---

## 🔁 10. Iterative Refinement

- Use follow-ups to progressively improve:

```markdown
Initial: Write a summary about electric cars.  
Follow-up: Now rewrite it in simpler language for a general audience.
```

---

## 🎛️ 11. Temperature and Creativity Control

- Use temperature to control creativity.
- Example:
  `Give three creative and unusual uses for an umbrella.`

---

## 🤖 12. Model-Specific Adjustments

- Customize based on strengths:
  - GPT-4: reasoning-heavy tasks
  - GPT-3.5: faster responses
  - LLaMA: local privacy

---

## 🔗 13. Prompt Chaining & Context Management

- Manage long conversations to stay within token limits.
- Summarize previous turns to retain important context.

---

## 🧭 14. Tone and Style Consistency

- Define the tone explicitly.
- Example:
  `Describe quantum mechanics in a humorous tone suitable for beginners.`

---

## 🚫 15. Error Prevention

- Instruct the model to admit uncertainty.
- Example:
  `Answer if you’re sure. Otherwise, reply with "I don’t know."`

---

## ✅ 16. Evaluation and Validation

- Ask the model to check its own output.
- Example:
  `List 5 cities in France, and double-check their spellings.`

---

## 🌍 17. Sensitivity & Inclusivity

- Encourage respectful and diverse perspectives.
- Example:
  `Describe the cultural impact of this holiday, ensuring inclusivity and sensitivity.`

---

## ⚡ 18. Efficiency & Sustainability

- Encourage short outputs to reduce token and energy usage.
- Example:
  `Briefly summarize renewable energy in fewer than 50 words.`

---

## 🍃 19. Energy Awareness (GreenPrompt Tip!)

- Promote sustainable usage:
  > “This prompt can be simplified to reduce tokens and energy usage.”

---

## ❌ Common Mistakes to Avoid

- Vague instructions like “tell me something”.
- Redundant phrases and excess politeness.
- No clear format instructions.
- Overloading prompt with irrelevant detail.

---

## ✅ Use These Best Practices To:

- Improve quality and relevance of AI outputs
- Reduce ambiguity and iteration cycles
- Enhance clarity, sustainability, and tone control

---

Happy Prompting! ✨
