"""One filter, two platforms.

Discord and YouTube each carried their own copy of this and they drifted.
The YouTube copy was five lines, "has a question mark or starts with a
question word", and it dropped 222 real requests that the Discord rules
catch: "Press F logic doesn't work for me in 5.4" has neither. The Discord
copy asks for 25 characters, which killed 33 real YouTube questions that
are simply terser than chat: "will this work in alsv4?".

Neither was wrong about its own channel. Keeping two copies was, so the one
thing that genuinely differs between them is the only parameter: how short
a real question is allowed to be.
"""
import re

# A comment is terser than a chat message. Both floors were measured
# against the archives rather than picked.
MIN_COMMENT = 15
MIN_CHAT = 25

QUESTION_WORDS = (
    "how", "what", "why", "where", "when", "which", "who", "can", "does",
    "do", "is", "are", "should", "would", "could", "any", "anyone", "help",
)

PROBLEM_MARKERS = (
    "doesn't work", "does not work", "dont work", "not working", "won't work",
    "wont work", "isn't working", "isnt working", "stopped working",
    "crash", "error", "bug", "broken", "stuck", "freeze", "glitch",
    "can't", "cant ", "cannot", "unable to", "fails", "failing", "failed",
    "issue", "problem", "not able", "no idea how", "dont know how",
    "don't know how", "i need help", "need help", "help me", "any help",
    "i need the", "i want to", "im trying", "i'm trying", "trying to",
    "does not have", "doesn't have", "i dont see", "i don't see",
    "not showing", "not appearing", "missing", "wrong",
)
# "the montage is not playing", "the trace is not detecting": the shape is
# "<thing> is not <verb>ing", which no single phrase above catches.
NEGATED_VERB = re.compile(
    r"\b(is|are|was|were|does|do|did|will|wont|won.t)\s+not\s+\w+")

# Every phrase above describes the thing that is broken. None describe the
# person, and someone already helped once often reports the second failure
# entirely in the first person: "aim and reload are still doing the same
# thing so now I'm stumped". Over the whole logged history this admits
# fourteen messages, so it is a narrow door, not a second front gate.
STUCK_REPORT = re.compile(
    r"\bi(?:.?m|\s+am)\s+(?:\w+\s+){0,2}"
    r"(?:stumped|stuck|lost|clueless|confused|struggling|at a loss)\b"
    # The fix was tried and it did not take.
    r"|\bstill\s+(?:doing the same|the same|not working|no luck|nothing)\b"
    # A question asked as a statement, which is how most follow-ups arrive.
    r"|\bi\s+(?:still\s+)?(?:dont|don.t|can.t|cant|cannot)\s+"
    r"(?:know|figure|understand|get)\s+(?:out\s+)?(?:why|how|what|where)\b")

# A message that is ONLY praise or thanks is not a request. "Only" is the
# whole rule: this is checked after the marker and question-word tests, so
# "Is it really not possible to do this... Awesome tutorial tho" is read as
# the question it is rather than dying on the word awesome.
CLOSERS = ("thank", "thanks", "tks", "obrigad", "worked", "solved", "fixed it",
           "amazing", "awesome", "great work", "great stuff", "congrat",
           "nice work", "love it", "keep it up", "well done")

# "Nice, if you need help, we're here" is someone offering, and it carries
# the same words as someone asking. Reading the offer as a request files a
# helper's kindness in the queue as work to do.
OFFERS = ("if you need help", "if u need help", "we're here", "were here",
          "happy to help", "here to help", "let me know if you need",
          "feel free to ask", "you can ask")

_URL_ONLY = re.compile(r"https?://\S+")


QUESTION = "question"
PRAISE = "praise"


def classify(text: str, min_len: int = MIN_CHAT) -> str:
    """QUESTION, PRAISE, or "" for neither.

    Praise used to be thrown away with the chatter. It is not work, but it
    is not noise either: it is the only record of what landed, and which
    video earned it. It comes back labelled so it can be read somewhere
    other than the queue of people waiting.
    """
    t = " ".join((text or "").split()).lower()
    # A pasted link with nothing around it says nothing to search on and
    # nothing to answer; the length test passes it because a URL is long,
    # and a YouTube link passes a bare question-mark test because of its
    # own query string.
    if len(_URL_ONLY.sub("", t).strip()) < min_len:
        return ""
    if len(t) < min_len:
        return ""
    if "?" not in t and any(o in t for o in OFFERS):
        return ""

    if (any(m in t for m in PROBLEM_MARKERS)
            or NEGATED_VERB.search(t)
            or STUCK_REPORT.search(t)):
        return QUESTION
    if "?" in t:
        return QUESTION
    if any(t.startswith(w + " ") for w in QUESTION_WORDS):
        return QUESTION
    # Nothing above it asked for anything. If it is warm, it is praise;
    # otherwise it is someone talking, which belongs nowhere.
    if any(c in t for c in CLOSERS):
        return PRAISE
    return ""


def looks_like_question(text: str, min_len: int = MIN_CHAT) -> bool:
    """Kept because most callers only ever wanted the one answer."""
    return classify(text, min_len) == QUESTION
