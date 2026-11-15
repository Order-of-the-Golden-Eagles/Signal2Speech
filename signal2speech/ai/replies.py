"""Reply suggestions for a typed question (#27). Pure Python, no Qt.

Every reply set becomes two Choices for SelectionHandler.begin_choice_round. A plain reply is
Choice(target, ActionIds.SPEAK_REPLY, text, text), so the tile shows the exact words that will be
spoken. Claude may instead suggest an app action (#106): show_satellite or compare_air_quality.
Those choices take their label and spoken text from the OpenOrbit dataset and contract, never from
model text, so the spoken numbers always match the map.
Each set carries its origin ("Claude", "Stub", or "Saved phrases") so the screen can say where
the words came from. Provider failures never raise to the UI: they fall back to saved phrases
with a note.
"""
from __future__ import annotations

import functools
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from signal2speech.core import ActionIds, Choice, TargetIds

ROOT = Path(__file__).resolve().parents[2]
MODEL = "claude-sonnet-5-5"
TIMEOUT_S = 8.0

CLAUDE, STUB, SAVED = "Claude", "Stub", "Saved phrases"
DEMO_ROUND = ROOT / "contracts" / "demo-round.json"
REPLY_ACTIONS = (ActionIds.SPEAK_REPLY, ActionIds.SHOW_SATELLITE, ActionIds.COMPARE_AIR_QUALITY)
ACTION_LABELS = {ActionIds.SHOW_SATELLITE: "Show the satellite view (shows the map)",
                 ActionIds.COMPARE_AIR_QUALITY: "Compare counties (shows the map)"}

SAVED_PHRASES: List[Tuple[str, str]] = [
    ("Yes.", "No."),
    ("Please give me a moment.", "Could you repeat the question?"),
    ("Thank you.", "I need help, please."),
    ("I'm comfortable.", "I'm in pain."),
    ("I agree.", "I don't agree."),
    ("Let's talk later.", "Please keep going."),
]


# ── Reply language (#194) ────────────────────────────────────
LANGUAGES: Dict[str, str] = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "it": "Italian", "vi": "Vietnamese", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "hi": "Hindi", "ar": "Arabic",
}
# Offline replies that exist in a language. Anything else falls back to English and says so.
SAVED_PHRASES_BY_LANGUAGE: Dict[str, List[Tuple[str, str]]] = {
    "es": [
        ("Sí.", "No."),
        ("Dame un momento, por favor.", "¿Puede repetir la pregunta?"),
        ("Gracias.", "Necesito ayuda, por favor."),
        ("Estoy bien.", "Me duele."),
        ("Estoy de acuerdo.", "No estoy de acuerdo."),
        ("Hablemos más tarde.", "Por favor, siga."),
    ],
}
HELP_PHRASES: Dict[str, str] = {"en": "I need help, please.", "es": "Necesito ayuda, por favor."}


def language_code(text: str) -> str:
    """"es", "ES", or "Spanish" -> "es". Raises ValueError for a language we don't list."""
    t = text.strip().lower()
    if t in LANGUAGES:
        return t
    for code, name in LANGUAGES.items():
        if name.lower() == t:
            return code
    raise ValueError(f"unknown reply language {text!r}; use one of: {', '.join(LANGUAGES)}")


def language_name(code: str) -> str:
    return LANGUAGES.get(code, code)


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


# ── OpenOrbit facts (#106) ───────────────────────────────────
@dataclass(frozen=True)
class OpenOrbitFacts:
    block: str                     # "Verified facts" text for the system prompt
    spoken: Dict[str, str]         # action id -> exact spoken text (dataset / contract)


@functools.lru_cache(maxsize=None)
def openorbit_facts() -> Optional[OpenOrbitFacts]:
    """Build the facts block from data/openorbit/ and contracts/demo-round.json. None if either
    is missing: Claude then gets no facts and app actions are refused."""
    from signal2speech.openorbit.dataset import AFTER, BEFORE, load_dataset
    try:
        ds = load_dataset()
        contract = json.loads(DEMO_ROUND.read_text(encoding="utf-8"))
        show = next(c["spokenText"] for c in contract["choices"]
                    if c["actionId"] == ActionIds.SHOW_SATELLITE)
    except (OSError, ValueError, KeyError, StopIteration):
        return None
    lines = ["Verified facts (the only facts you may state):",
             "Event: wildfire smoke reached southeast Michigan in late June 2023.",
             f"Daily AQI by county from U.S. EPA AirData ({BEFORE} before the smoke, "
             f"{AFTER} during it):"]
    for c in ds.changes:
        verb = "rose" if c.change >= 0 else "fell"
        lines.append(f"- {c.county} County: {c.before} ({c.before_category}) on {BEFORE}, "
                     f"{c.after} ({c.after_category}) on {AFTER}; {verb} {abs(c.change)} points.")
    up, high = ds.largest_increase(), ds.highest_after()
    lines.append(f"- Larger increase: {up.county} ({up.change:+d} points). "
                 f"Higher AQI on {AFTER}: {high.county} ({high.after}).")
    for pl in ds.places:
        lines.append(f"- {pl.label} ({pl.short}) is in {pl.county} County.")
    lines.append(f"- Satellite imagery: NASA GIBS / Worldview, MODIS ({ds.layer}), "
                 f"for {BEFORE} and {AFTER}.")
    lines.append("- Sources: NASA GIBS MODIS imagery; U.S. EPA AirData daily AQI by county.")
    return OpenOrbitFacts("\n".join(lines), {ActionIds.SHOW_SATELLITE: show,
                                              ActionIds.COMPARE_AIR_QUALITY: ds.spoken_comparison()})


def build_choices(items: Sequence, max_chars: int = 120) -> Tuple[Choice, ...]:
    """items: two plain strings, or two (text, action) pairs. An app action gets its label and
    spoken text from OpenOrbit facts and the model text is dropped. Raises ProviderError."""
    items = list(items)
    if all(isinstance(i, str) for i in items):
        return to_choices(validate(items, max_chars))
    try:
        pairs = [(i, ActionIds.SPEAK_REPLY) if isinstance(i, str) else (i[0], i[1])
                 for i in items]
    except (TypeError, IndexError):
        raise ProviderError("provider returned malformed replies") from None
    if len(pairs) != 2:
        raise ProviderError("provider did not return two replies")
    if any(a not in REPLY_ACTIONS for _, a in pairs):
        raise ProviderError("provider suggested an unknown action")
    out = []
    for target, (text, action) in zip((TargetIds.TARGET_1, TargetIds.TARGET_2), pairs):
        if action == ActionIds.SPEAK_REPLY:
            text = " ".join(str(text).split())
            if not text:
                raise ProviderError("provider did not return two replies")
            if len(text) > max_chars:
                raise ProviderError("provider reply too long")
            out.append(Choice(target, action, text, text))
        else:
            facts = openorbit_facts()
            if facts is None:
                raise ProviderError("OpenOrbit data missing for the suggested action")
            out.append(Choice(target, action, ACTION_LABELS[action], facts.spoken[action]))
    a, b = out
    if a.action_id == b.action_id != ActionIds.SPEAK_REPLY or \
            a.spoken_text.casefold() == b.spoken_text.casefold():
        raise ProviderError("provider returned the same reply twice")
    return a, b


class SavedPhrases:
    """Offline pairs. next_page() cycles so judges can offer other saved phrases."""

    def __init__(self, pairs: Sequence[Tuple[str, str]] = tuple(SAVED_PHRASES)):
        self.pairs = list(pairs)
        self.index = 0
        self.english_only_note = ""   # set when the reply language has no saved phrases (#194)

    def current(self, note: str = "") -> ReplySet:
        if self.english_only_note:
            note = f"{note}; {self.english_only_note}" if note else self.english_only_note
        return ReplySet(to_choices(self.pairs[self.index]), SAVED, note)

    def next_page(self, note: str = "") -> ReplySet:
        self.index = (self.index + 1) % len(self.pairs)
        return self.current(note)


# ── Editable saved phrases (#134) ────────────────────────────
PHRASES_FILE = ROOT / "data" / "phrases.json"


def load_saved_phrases(path: Path = PHRASES_FILE) -> Tuple[List[Tuple[str, str]], str]:
    """Pairs from data/phrases.json if it's valid, else the built-in list. Never raises.

    Returns (pairs, note); the note says where the phrases came from, or why the file was skipped.
    """
    builtin = list(SAVED_PHRASES)
    if not path.is_file():
        return builtin, f"built-in (no {path.name})"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return builtin, f"built-in ({path.name} unreadable: {type(e).__name__})"
    raw = data.get("pairs") if isinstance(data, dict) else data
    if not isinstance(raw, list) or not raw:
        return builtin, f"built-in ({path.name} has no \"pairs\" list)"
    pairs: List[Tuple[str, str]] = []
    for i, pair in enumerate(raw, 1):
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(t, str) for t in pair)):
            return builtin, f"built-in ({path.name} pair {i} isn't two strings)"
        try:
            a, b = validate(pair)
        except ProviderError as e:
            return builtin, f"built-in ({path.name} pair {i}: {e.args[0].replace('provider ', '')})"
        pairs.append((a, b))
    return pairs, f"{path.name} ({len(pairs)} pairs)"


def saved_phrases_from_file(path: Path = PHRASES_FILE) -> "SavedPhrases":
    pairs, note = load_saved_phrases(path)
    saved = SavedPhrases(pairs)
    saved.source = note
    return saved

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
FACT_RULES = (
    "Rules for facts: state facts only from the verified facts below. Never invent numbers, "
    "dates, places, or comparisons. If a question needs facts that are not listed, offer "
    "replies such as a short, honest \"I don't know\" and a request for a moment.\n\n"
    "App actions: each reply has an action. Use \"speak_reply\" for ordinary replies; the app "
    "speaks your words. Use \"compare_air_quality\" when a reply should answer with the county "
    "AQI comparison, or \"show_satellite\" when it should show the satellite view of the "
    "smoke. For those two the app shows the map and speaks its own verified line, so keep "
    "that reply text to a short summary. The two replies must differ."
)


def system_prompt(facts: Optional[OpenOrbitFacts], language: str = "en") -> str:
    """Byte-stable for a given dataset and language (no timestamps), so every call sends the
    same prompt. A non-English language asks for the replies in that language (#194)."""
    base = SYSTEM_PROMPT
    if language != "en":
        name = language_name(language)
        base = base.replace("Use plain spoken English", f"Write both replies in plain spoken {name}")
        base += (f" The person will hear the replies in {name}, so never mix in English. For an "
                 "app action the app speaks its own verified English line.")
    if facts is None:
        return (base + "\n\nNo verified facts are available. Never state facts or "
                "numbers, and use \"speak_reply\" for both replies.")
    return base + "\n\n" + FACT_RULES + "\n\n" + facts.block


REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply_a": {"type": "string"}, "action_a": {"enum": list(REPLY_ACTIONS)},
                   "reply_b": {"type": "string"}, "action_b": {"enum": list(REPLY_ACTIONS)}},
    "required": ["reply_a", "action_a", "reply_b", "action_b"],
    "additionalProperties": False,
}


class ClaudeProvider:
    """Claude via the Anthropic SDK. Short timeout, no retries: the fallback is the retry."""

    name = CLAUDE

    def __init__(self, api_key: str, model: str = MODEL, timeout: float = TIMEOUT_S,
                 client=None, language: str = "en"):
        import anthropic  # lazy: the app runs offline without the SDK
        self._anthropic = anthropic
        self.model = model
        self.client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout,
                                                    max_retries=0)
        self.set_language(language)

    def set_language(self, code: str) -> bool:
        """Claude can write in any listed language: the language goes in the prompt (#194)."""
        self.language = code
        self.system = system_prompt(openorbit_facts(), code)
        return True

    def replies(self, question: str, avoid: Sequence[str] = ()) -> List[Tuple[str, str]]:
        """Two (text, action) pairs. ReplySuggester maps actions to app Choices."""
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
                system=self.system,
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
            return [(data["reply_a"], data.get("action_a", ActionIds.SPEAK_REPLY)),
                    (data["reply_b"], data.get("action_b", ActionIds.SPEAK_REPLY))]
        except (ValueError, KeyError, TypeError) as e:
            raise ProviderError("provider returned malformed replies") from e


class StubProvider:
    """Labelled stand-in for rehearsal while provider setup is pending. delay > timeout
    rehearses the timeout fallback."""

    name = STUB
    PAIRS = [("Yes, that works for me.", "No, I'd rather not."),
             ("I think so, yes.", "I'm not sure yet."),
             ("That sounds good.", "Can we talk about it later?")]
    PAIRS_BY_LANGUAGE = {"es": [("Sí, me parece bien.", "No, prefiero que no."),
                                ("Creo que sí.", "Todavía no lo sé."),
                                ("Suena bien.", "¿Podemos hablarlo más tarde?")]}

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self._i = -1
        self.language = "en"

    def set_language(self, code: str) -> bool:
        """True if the stub has replies in `code`; otherwise it stays English."""
        ok = code == "en" or code in self.PAIRS_BY_LANGUAGE
        self.language = code if ok else "en"
        return ok

    def replies(self, question: str, avoid: Sequence[str] = ()) -> List[str]:
        if self.delay:
            time.sleep(self.delay)
        pairs = self.PAIRS_BY_LANGUAGE.get(self.language, self.PAIRS)
        self._i = (self._i + 1) % len(pairs)
        return list(pairs[self._i])


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
        self._saved_by_language = {"en": self.saved}
        self.language = "en"

    def set_language(self, code: str) -> str:
        """Ask the provider and the saved phrases for `code` (#194). Returns a note naming
        anything that stays English, or "" if everything switched."""
        notes = []
        if self.provider is not None and hasattr(self.provider, "set_language"):
            if not self.provider.set_language(code):
                notes.append(f"{self.provider.name} replies are English only")
        if code not in self._saved_by_language:
            if code in SAVED_PHRASES_BY_LANGUAGE:
                sp = SavedPhrases(SAVED_PHRASES_BY_LANGUAGE[code])
                sp.source = f"built-in {language_name(code)}"
            else:
                sp = SavedPhrases(self._saved_by_language["en"].pairs)
                sp.source = getattr(self._saved_by_language["en"], "source", "built-in")
                sp.english_only_note = "saved phrases are English only"
            self._saved_by_language[code] = sp
        self.saved = self._saved_by_language[code]
        if self.saved.english_only_note:
            notes.append(self.saved.english_only_note)
        self.language = code
        return "; ".join(notes)

    def suggest(self, question: str, avoid: Sequence[str] = ()) -> ReplySet:
        if not question.strip():
            return self.saved.current("no question typed")
        if self.provider is None:
            return self.saved.current("no provider")
        try:
            choices = build_choices(self.provider.replies(question.strip(), avoid))
        except ProviderError as e:
            return self.saved.current(str(e))
        except Exception as e:  # a provider bug must not take the demo down
            return self.saved.current(f"provider failed ({type(e).__name__})")
        return ReplySet(choices, self.provider.name)
