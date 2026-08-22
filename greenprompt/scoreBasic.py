"""
scoreBasic.py — Offline prompt quality scorer using NLTK and regex.

Implements score_prompt(), which evaluates a prompt on 18 dimensions derived
from the RTCF framework (Role, Task, Context, Format) and established prompt
engineering best practices. The scorer requires no network access and no LLM
call — it runs entirely on NLTK POS tagging and pattern matching.

Maximum total score: 50 points. Score% = (total / 50) * 100.

Dimensions: RTCF Structure, Clarity & Specificity, Conciseness, Contextual
Priming, Output Specification, Instructional Tone, Examples & Few-Shot, Task
Decomposition, Positive/Negative Examples, Iterative Refinement, Creativity
Control, Tone & Style, Error Prevention, Evaluation & Validation, Sensitivity
& Inclusivity, Efficiency & Sustainability, Energy Awareness, Keyword Richness.

See docs/prompt-scoring.md for a full reference with examples.
"""

import re
import nltk
from nltk.corpus import stopwords

#: NLTK resources this module needs, as (download name, nltk.data.find path).
#: Both the legacy and the >=3.9 resource names are listed because which one
#: NLTK looks for depends on its version, and having the other present is
#: harmless.
_NLTK_RESOURCES = (
    ("punkt", "tokenizers/punkt"),
    ("punkt_tab", "tokenizers/punkt_tab"),
    ("averaged_perceptron_tagger", "taggers/averaged_perceptron_tagger"),
    ("averaged_perceptron_tagger_eng", "taggers/averaged_perceptron_tagger_eng"),
    ("wordnet", "corpora/wordnet"),
    ("stopwords", "corpora/stopwords"),
)

#: Set once ensure_nltk_data() has confirmed every resource is present, so the
#: check costs nothing after the first scored prompt.
_nltk_data_ready = False


def ensure_nltk_data(force=False):
    """
    Make sure the NLTK corpora this module needs are available locally.

    Downloads only what is actually missing, and only the first time it is
    called. This deliberately does not run at import time: `cli.py` imports
    this module unconditionally, so downloading on import made every single
    command — `greenprompt --help` included — attempt four network round
    trips before printing anything.

    Args:
        force: Re-check every resource even if a previous call succeeded.
    """
    global _nltk_data_ready
    if _nltk_data_ready and not force:
        return
    for name, path in _NLTK_RESOURCES:
        try:
            nltk.data.find(path)
        except LookupError:
            nltk.download(name, quiet=True)
    _nltk_data_ready = True


def normalize(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


#: Instruction verbs that commonly open a prompt. Used for two things: deciding
#: whether a sentence-initial token is an imperative verb (see get_verbs), and
#: deciding whether a prompt states an explicit task (see has_explicit_task).
#:
#: One shared vocabulary, because a word that makes something a task ought also
#: to count as a verb.
INSTRUCTION_VERBS = frozenset(
    {
        # original core task verbs
        "analyze",
        "categorize",
        "classify",
        "compare",
        "compose",
        "define",
        "describe",
        "evaluate",
        "explain",
        "extract",
        "generate",
        "list",
        "review",
        "solve",
        "summarize",
        "translate",
        "write",
        # common instruction verbs that were previously unrecognised
        "answer",
        "build",
        "calculate",
        "check",
        "compute",
        "convert",
        "count",
        "create",
        "critique",
        "debug",
        "demonstrate",
        "derive",
        "design",
        "draft",
        "elaborate",
        "estimate",
        "expand",
        "explore",
        "find",
        "fix",
        "format",
        "give",
        "group",
        "identify",
        "illustrate",
        "implement",
        "improve",
        "interpret",
        "introduce",
        "justify",
        "label",
        "make",
        "name",
        "outline",
        "plan",
        "predict",
        "produce",
        "prove",
        "provide",
        "rank",
        "recommend",
        "refactor",
        "rephrase",
        "rewrite",
        "revise",
        "score",
        "search",
        "show",
        "simplify",
        "simulate",
        "sort",
        "suggest",
        "tell",
        "test",
        "transform",
        "validate",
        "verify",
    }
)


def _sentence_initial_imperatives(text):
    """
    Return the leading word of each sentence that is a known instruction verb.

    NLTK's POS tagger labels a capitalised sentence-opening verb as a proper
    noun often enough to matter: "Summarize this article." tags correctly, but
    "Explain inertia.", "List three benefits." and "Define entropy." do not.
    Whether a prompt was credited therefore depended on which verb it happened
    to start with — not a defensible scoring rule, and it penalised the bare
    imperative, which is the most natural way to write a prompt.

    Lowercasing before tagging and prepending a sentinel word were both tried
    and measured; each fixes some words and breaks others. Matching against a
    known vocabulary is the only approach that behaves consistently.

    This is a heuristic and will occasionally fire on a noun ("List of items"),
    which is an acceptable trade in a scorer that already relies on regex
    matching throughout.

    Sentences are split on terminal punctuation and newlines rather than with
    nltk.sent_tokenize, so this needs no extra corpus and stays deterministic.
    """
    found = []
    for sentence in re.split(r"[.!?\n]+", text):
        words = re.findall(r"[A-Za-z']+", sentence)
        if words and words[0].lower() in INSTRUCTION_VERBS:
            found.append(words[0])
    return found


def get_verbs(text):
    """
    Return the verbs in `text`.

    POS tagging supplies the general case; sentence-initial instruction verbs
    are added on top because the tagger mislabels them (see
    _sentence_initial_imperatives). Order is tagger results first, then any
    imperatives the tagger missed, with duplicates removed.
    """
    ensure_nltk_data()
    tokens = nltk.word_tokenize(text)
    pos_tags = nltk.pos_tag(tokens)
    verbs = [word for word, tag in pos_tags if tag.startswith("VB")]

    seen = {v.lower() for v in verbs}
    for word in _sentence_initial_imperatives(text):
        if word.lower() not in seen:
            verbs.append(word)
            seen.add(word.lower())
    return verbs


def count_unique_keywords(text):
    ensure_nltk_data()
    stop_words = set(stopwords.words("english"))
    words = nltk.word_tokenize(text)
    return len(
        set([w.lower() for w in words if w.lower() not in stop_words and w.isalpha()])
    )


def has_explicit_role(text):
    patterns = [r"you are (an?|the)?\s?\w+", r"pretend to be", r"act as", r"role:"]
    return any(re.search(p, text, re.I) for p in patterns)


def has_explicit_task(text):
    """True if the prompt names a task using a recognised instruction verb."""
    return any(v.lower() in INSTRUCTION_VERBS for v in get_verbs(text))


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
    """
    Score a prompt on 18 quality dimensions.

    Evaluates the prompt using regex patterns and NLTK POS tagging. All
    processing is local — no API calls are made.

    Args:
        prompt: The raw prompt string to evaluate.

    Returns:
        dict with keys:
            total_score (int): Sum of all dimension scores.
            max_score (int): Maximum possible score (50).
            score_percent (float): total_score / max_score * 100.
            details (dict): Per-dimension scores keyed by dimension name.
    """
    ensure_nltk_data()
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
