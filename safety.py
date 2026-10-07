"""Safety gate: OpenAI's free moderation endpoint screens every request before the brain sees it."""
import os


def screen(text):
    """Return (ok, reason). Skips the check when no OPENAI_API_KEY is set."""
    if not os.environ.get("OPENAI_API_KEY"):
        return True, "no gate"
    from openai import OpenAI
    r = OpenAI().moderations.create(model="omni-moderation-latest", input=text).results[0]
    if r.flagged:
        cats = [k for k, v in r.categories.model_dump().items() if v]
        return False, ", ".join(cats)
    return True, "passed"
