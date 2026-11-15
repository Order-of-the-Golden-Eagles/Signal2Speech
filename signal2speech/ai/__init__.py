"""AI Answering (#5, #27, #106): reply choices for a typed question, with saved-phrase fallback."""
from .replies import (CLAUDE, MODEL, PHRASES_FILE, SAVED, SAVED_PHRASES, STUB, ClaudeProvider,
                      ProviderError, ReplySet, ReplySuggester, SavedPhrases, StubProvider,
                      build_choices, load_dotenv, load_saved_phrases, make_provider,
                      openorbit_facts, saved_phrases_from_file, system_prompt, to_choices,
                      validate)

__all__ = ["CLAUDE", "MODEL", "PHRASES_FILE", "SAVED", "SAVED_PHRASES", "STUB", "ClaudeProvider",
           "ProviderError", "ReplySet", "ReplySuggester", "SavedPhrases", "StubProvider",
           "build_choices", "load_dotenv", "load_saved_phrases", "make_provider",
           "openorbit_facts", "saved_phrases_from_file", "system_prompt", "to_choices",
           "validate"]
