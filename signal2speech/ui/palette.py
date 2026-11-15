"""Back-compat alias (#135). The design now lives in theme.py (#174); import from there."""
from .theme import *  # noqa: F401,F403
from .theme import TEXT_PAIRS  # noqa: F401  (explicit, for readers)
