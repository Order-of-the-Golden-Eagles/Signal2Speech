"""AI Answering (#5, #27, #106): reply choices for a typed question, with saved-phrase fallback."""
from .replies import (CLAUDE, MODEL, SAVED, SAVED_PHRASES, STUB, ClaudeProvider, ProviderError,
                      ReplySet, ReplySuggester, SavedPhrases, StubProvider, build_choices,
                      load_dotenv, make_provider, openorbit_facts, system_prompt, to_choices,
                      validate)

__all__ = ["CLAUDE", "MODEL", "SAVED", "SAVED_PHRASES", "STUB", "ClaudeProvider", "ProviderError",
           "ReplySet", "ReplySuggester", "SavedPhrases", "StubProvider", "build_choices",
           "load_dotenv", "make_provider", "openorbit_facts", "system_prompt", "to_choices",
           "validate"]
