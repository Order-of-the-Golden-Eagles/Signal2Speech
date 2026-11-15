"""AI Answering (#5, #27): reply choices for a typed question, with saved-phrase fallback."""
from .replies import (CLAUDE, MODEL, PHRASES_FILE, SAVED, SAVED_PHRASES, STUB, ClaudeProvider, ProviderError,
                      ReplySet, ReplySuggester, SavedPhrases, StubProvider, load_dotenv,
                      load_saved_phrases, make_provider, saved_phrases_from_file, to_choices,
                      validate)

__all__ = ["CLAUDE", "MODEL", "PHRASES_FILE", "SAVED", "SAVED_PHRASES", "STUB", "ClaudeProvider", "ProviderError",
           "ReplySet", "ReplySuggester", "SavedPhrases", "StubProvider", "load_dotenv",
           "load_saved_phrases", "make_provider", "saved_phrases_from_file", "to_choices",
           "validate"]
