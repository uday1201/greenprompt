import re
import nltk
from nltk.corpus import stopwords

nltk.download("punkt", quiet=True)
nltk.download("averaged_perceptron_tagger", quiet=True)
nltk.download("wordnet", quiet=True)
nltk.download("stopwords", quiet=True)


def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def get_verbs(text):
    tokens = nltk.word_tokenize(text)
    pos_tags = nltk.pos_tag(tokens)
    return [word for word, tag in pos_tags if tag.startswith("VB")]


def count_unique_keywords(text):
    stop_words = set(stopwords.words("english"))
    words = nltk.word_tokenize(text)
    return len(
        set([w.lower() for w in words if w.lower() not in stop_words and w.isalpha()])
    )


def has_explicit_role(text):
    patterns = [r"you are (an?|the)?\s?\w+", r"pretend to be", r"act as", r"role:"]
    return any(re.search(p, text, re.I) for p in patterns)


def has_explicit_task(text):
    verbs = get_verbs(text)
    # Strong action verbs for tasks
    core_verbs = set(
        [
            "summarize",
            "list",
            "explain",
            "describe",
            "define",
            "compare",
            "generate",
            "analyze",
            "write",
            "compose",
            "translate",
            "solve",
            "classify",
            "extract",
            "categorize",
            "review",
            "evaluate",
        ]
    )
    return any(v.lower() in core_verbs for v in verbs)


def has_context(text):
    patterns = [r"context:", r"background:", r"for\s+\w+", r"audience:"]
    return any(re.search(p, text, re.I) for p in patterns)


def has_format(text):
    patterns = [
        r"format:",
        r"output as",
        r"provide.*(table|bullets|list|json|csv|markdown)",
    ]
    return any(re.search(p, text, re.I) for p in patterns)


def has_examples(text):
    # Detect inline or few-shot examples
    patterns = [r"example:", r"Q:", r"A:", r"sample output", r"for instance", r"e\.g\."]
    return any(re.search(p, text, re.I) for p in patterns)


def has_task_decomposition(text):
    # Look for sequences: "First ... Then ..." or stepwise instructions
    return bool(
        re.search(r"first.*then", text, re.I) or re.search(r"step [0-9]", text, re.I)
    )


def positive_negative_examples(text):
    # Look for inclusion/exclusion rules
    return bool(re.search(r"(do not|exclude|not include|except)", text, re.I))


def iterative_refinement(text):
    # Look for iterative wording
    return bool(re.search(r"(revise|improve|refine|rewrite|repeat)", text, re.I))


def creativity_control(text):
    # Look for explicit creativity control or style cues
    return bool(
        re.search(
            r"(creative|imaginative|unusual|original|unique|be bold|inventive)",
            text,
            re.I,
        )
    )


def tone_style(text):
    # Look for tone or style specifications
    return bool(
        re.search(
            r"(tone:|style:|use a .+ tone|in a .+ style|formal|casual|friendly|professional|humorous|serious)",
            text,
            re.I,
        )
    )


def error_prevention(text):
    return bool(
        re.search(
            r"(do not guess|only answer if sure|if unsure, say so|if you do not know)",
            text,
            re.I,
        )
    )


def eval_validation(text):
    return bool(
        re.search(
            r"(double-check|verify|validate|ensure accuracy|cross-check|review your answer)",
            text,
            re.I,
        )
    )


def sensitivity_inclusivity(text):
    return bool(
        re.search(
            r"(inclusive|respectful|avoid bias|unbiased|sensitive to)", text, re.I
        )
    )


def brevity_eco(text):
    return bool(
        re.search(
            r"(concise|briefly|short answer|max \d+ words|minimize tokens|eco-friendly|efficient)",
            text,
            re.I,
        )
    )


def energy_awareness(text):
    return bool(
        re.search(
            r"(energy usage|carbon|footprint|sustainable|green|efficient)", text, re.I
        )
    )


def score_prompt(prompt):
    prompt_norm = normalize(prompt)
    score_details = {}

    # RTCF Structure
    score_details["RTCF Structure"] = (
        int(has_explicit_role(prompt_norm))
        + int(has_explicit_task(prompt_norm))
        + int(has_context(prompt_norm))
        + int(has_format(prompt_norm))
    )

    # Clarity & Specificity
    score_details["Clarity & Specificity"] = (
        5
        if has_explicit_task(prompt_norm) and len(prompt) < 400
        else 3
        if has_explicit_task(prompt_norm)
        else 0
    )

    # Conciseness
    fillers = [
        "could you",
        "please",
        "would you mind",
        "kindly",
        "if possible",
        "try to",
        "attempt to",
        "please try",
        "just",
        "simply",
        "I would like you to",
        "I want you to",
        "can you",
        "could you",
    ]
    filler_count = sum(prompt_norm.count(f) for f in fillers)
    score_details["Conciseness"] = 5 - min(filler_count, 5)

    # Contextual Priming
    score_details["Contextual Priming"] = 3 if has_context(prompt_norm) else 0

    # Output Specification
    score_details["Output Specification"] = 5 if has_format(prompt_norm) else 0

    # Instructional Tone
    instr_verbs = get_verbs(prompt)
    score_details["Instructional Tone"] = 3 if len(instr_verbs) > 0 else 0

    # Examples & Few-Shot Learning
    score_details["Examples & Few-Shot"] = 2 if has_examples(prompt_norm) else 0

    # Task Decomposition
    score_details["Task Decomposition"] = (
        2 if has_task_decomposition(prompt_norm) else 0
    )

    # Positive & Negative Examples
    score_details["Positive/Negative Examples"] = (
        2 if positive_negative_examples(prompt_norm) else 0
    )

    # Iterative Refinement
    score_details["Iterative Refinement"] = (
        2 if iterative_refinement(prompt_norm) else 0
    )

    # Creativity Control
    score_details["Creativity Control"] = 2 if creativity_control(prompt_norm) else 0

    # Tone & Style Consistency
    score_details["Tone & Style"] = 2 if tone_style(prompt_norm) else 0

    # Error Prevention
    score_details["Error Prevention"] = 2 if error_prevention(prompt_norm) else 0

    # Evaluation & Validation
    score_details["Evaluation & Validation"] = 2 if eval_validation(prompt_norm) else 0

    # Sensitivity & Inclusivity
    score_details["Sensitivity & Inclusivity"] = (
        2 if sensitivity_inclusivity(prompt_norm) else 0
    )

    # Efficiency & Sustainability
    score_details["Efficiency & Sustainability"] = 2 if brevity_eco(prompt_norm) else 0

    # Energy Awareness
    score_details["Energy Awareness"] = 2 if energy_awareness(prompt_norm) else 0

    # Keyword Richness (bonus: how many non-stopword, non-filler unique tokens)
    kw_count = count_unique_keywords(prompt)
    score_details["Keyword Richness"] = (
        2 if kw_count >= 5 else 1 if kw_count >= 2 else 0
    )

    total_score = sum(score_details.values())
    max_score = 50  # Adjust as per your parameter count/weighting

    return {
        "total_score": total_score,
        "max_score": max_score,
        "score_percent": (total_score / max_score) * 100,
        "details": score_details,
    }
