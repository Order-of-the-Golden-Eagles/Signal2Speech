"""AI Answering (#5, #27): reply choices for a typed question, with saved-phrase fallback."""
from .replies import (CLAUDE, MODEL, SAVED, SAVED_PHRASES, STUB, ClaudeProvider, ProviderError,
                      ReplySet, ReplySuggester, SavedPhrases, StubProvider, load_dotenv,
                      make_provider, to_choices, validate)

__all__ = ["CLAUDE", "MODEL", "SAVED", "SAVED_PHRASES", "STUB", "ClaudeProvider", "ProviderError",
           "ReplySet", "ReplySuggester", "SavedPhrases", "StubProvider", "load_dotenv",
           "make_provider", "to_choices", "validate"]
