"""Reply suggestions for a typed question (#27). Pure Python, no Qt.

Every reply set becomes two Choice(target, ActionIds.SPEAK_REPLY, text, text) for
SelectionHandler.begin_choice_round. The tile shows the exact words that will be spoken.
Each set carries its origin ("Claude", "Stub", or "Saved phrases") so the screen can say where
the words came from. Provider failures never raise to the UI: they fall back to saved phrases
with a note.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from signal2speech.core import ActionIds, Choice, TargetIds

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-opus-5-5"
TIMEOUT_S = 8.0

CLAUDE, STUB, SAVED = "Claude", "Stub", "Saved phrases"

SAVED_PHRASES: List[Tuple[str, str]] = [
    ("Yes.", "No."),
    ("Please give me a moment.", "Could you repeat the question?"),
    ("Thank you.", "I need help, please."),
    ("I'm comfortable.", "I'm in pain."),
    ("I agree.", "I don't agree."),
    ("Let's talk later.", "Please keep going."),
]


class ProviderError(Exception):
    """A provider could not produce two usable replies. The message is shown to judges."""


@dataclass(frozen=True)
class ReplySet:
    choices: Tuple[Choice, ...]
    origin: str            # CLAUDE, STUB, or SAVED
    note: str = ""         # why this origin, e.g. "timeout after 8 s"

    @property
    def texts(self) -> List[str]:
        return [c.spoken_text for c in self.choices]


def to_choices(texts: Sequence[str]) -> Tuple[Choice, ...]:
    a, b = texts
    return (Choice(TargetIds.TARGET_1, ActionIds.SPEAK_REPLY, a, a),
            Choice(TargetIds.TARGET_2, ActionIds.SPEAK_REPLY, b, b))


def validate(texts: Sequence[str], max_chars: int = 120) -> List[str]:
    clean = [" ".join(str(t).split()) for t in texts]
    if len(clean) != 2 or not all(clean):
        raise ProviderError("provider did not return two replies")
    if clean[0].casefold() == clean[1].casefold():
        raise ProviderError("provider returned the same reply twice")
    if any(len(t) > max_chars for t in clean):
        raise ProviderError("provider reply too long")
    return clean


class SavedPhrases:
    """Offline pairs. next_page() cycles so judges can offer other saved phrases."""

    def __init__(self, pairs: Sequence[Tuple[str, str]] = tuple(SAVED_PHRASES)):
        self.pairs = list(pairs)
        self.index = 0

    def current(self, note: str = "") -> ReplySet:
        return ReplySet(to_choices(self.pairs[self.index]), SAVED, note)

    def next_page(self, note: str = "") -> ReplySet:
        self.index = (self.index + 1) % len(self.pairs)
        return self.current(note)


# ── Providers ────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You write reply options for a person who can't speak or type. They answer a "
    "conversation partner by choosing one of two options with a brain-computer interface, "
    "and the app speaks the chosen option aloud word for word.\n\n"
    "Given the partner's question, write two replies in the first person, each under 12 "
    "words, that a person might actually say. Make them clearly different (for example, "
    "agree and disagree, or two different answers) so the choice is meaningful. Use plain "
    "spoken English with no emojis or stage directions. If the question needs facts only "
    "the person knows, offer natural options such as a short answer and a request for a "
    "moment to think."
)
REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply_a": {"type": "string"}, "reply_b": {"type": "string"}},
    "required": ["reply_a", "reply_b"],
    "additionalProperties": False,
}


class ClaudeProvider:
    """Claude via the Anthropic SDK. Short timeout, no retries: the fallback is the retry."""

    name = CLAUDE

    def __init__(self, api_key: str, model: str = MODEL, timeout: float = TIMEOUT_S,
                 client=None):
        import anthropic  # lazy: the app runs offline without the SDK
        self._anthropic = anthropic
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout,
                                                    max_retries=0)

    def replies(self, question: str, avoid: Sequence[str] = ()) -> List[str]:
        a = self._anthropic
        content = f"Question: {question}"
        if avoid:
            content += "\nAlready offered, so write different replies: " + " | ".join(avoid)
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=SYSTEM_PROMPT,
                output_config={"effort": "low",
                               "format": {"type": "json_schema", "schema": REPLY_SCHEMA}},
                messages=[{"role": "user", "content": content}],
            )
        except a.APITimeoutError as e:
            raise ProviderError("provider timeout") from e
        except a.AuthenticationError as e:
            raise ProviderError("invalid API key") from e
        except a.RateLimitError as e:
            raise ProviderError("provider rate limited") from e
        except a.APIStatusError as e:
            raise ProviderError(f"provider error {e.status_code}") from e
        except a.APIConnectionError as e:
            raise ProviderError("offline: no connection to provider") from e
        if resp.stop_reason == "refusal":
            raise ProviderError("provider declined the question")
        if resp.stop_reason == "max_tokens":
            raise ProviderError("provider reply cut off")
        text = next((b.text for b in resp.content if b.type == "text"), None)
        try:
            data = json.loads(text or "")
            return [data["reply_a"], data["reply_b"]]
        except (ValueError, KeyError, TypeError) as e:
            raise ProviderError("provider returned malformed replies") from e


class StubProvider:
    """Labelled stand-in for rehearsal while provider setup is pending. delay > timeout
    rehearses the timeout fallback."""

    name = STUB
    PAIRS = [("Yes, that works for me.", "No, I'd rather not."),
             ("I think so, yes.", "I'm not sure yet."),
             ("That sounds good.", "Can we talk about it later?")]

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self._i = -1

    def replies(self, question: str, avoid: Sequence[str] = ()) -> List[str]:
        if self.delay:
            time.sleep(self.delay)
        self._i = (self._i + 1) % len(self.PAIRS)
        return list(self.PAIRS[self._i])


# ── Setup ────────────────────────────────────────────────────
def load_dotenv(path: Path = ROOT / ".env", env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Read KEY=VALUE lines into env without overriding values already set. Never logs values."""
    env = os.environ if env is None else env
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.removeprefix("export ").partition("=")
            env.setdefault(key.strip(), value.strip().strip("'\""))
    return env


def make_provider(kind: str = "auto", env: Optional[Mapping[str, str]] = None,
                  timeout: float = TIMEOUT_S):
    """Return (provider or None, note). None means saved phrases only."""
    env = load_dotenv() if env is None else env
    if kind == "saved":
        return None, "saved phrases only (--provider saved)"
    if kind == "stub":
        return StubProvider(), "Stub: provider setup pending"
    if kind == "slow-stub":
        return StubProvider(delay=timeout + 30), "Stub that never answers in time (timeout rehearsal)"
    if kind not in ("auto", "claude"):
        raise ValueError(f"Unknown provider: {kind}")
    key = env.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        if kind == "claude":
            raise ValueError("--provider claude needs ANTHROPIC_API_KEY in .env")
        return StubProvider(), "Stub: provider setup pending (no ANTHROPIC_API_KEY in .env)"
    try:
        return ClaudeProvider(key, timeout=timeout), f"Claude ({MODEL})"
    except ImportError:
        if kind == "claude":
            raise ValueError("--provider claude needs the anthropic package (pip install anthropic)")
        return StubProvider(), "Stub: anthropic package not installed"


class ReplySuggester:
    """Synchronous suggest(). Run it off the UI thread (see ai.qt.AsyncSuggester)."""

    def __init__(self, provider=None, saved: Optional[SavedPhrases] = None):
        self.provider = provider
        self.saved = saved or SavedPhrases()

    def suggest(self, question: str, avoid: Sequence[str] = ()) -> ReplySet:
        if not question.strip():
            return self.saved.current("no question typed")
        if self.provider is None:
            return self.saved.current("no provider")
        try:
            texts = validate(self.provider.replies(question.strip(), avoid))
        except ProviderError as e:
            return self.saved.current(str(e))
        except Exception as e:  # a provider bug must not take the demo down
            return self.saved.current(f"provider failed ({type(e).__name__})")
        return ReplySet(to_choices(texts), self.provider.name)
