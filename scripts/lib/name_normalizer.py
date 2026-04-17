"""
Player name normalization utilities.

Standard: SURNAME Given_name
  - Surname tokens are ALL UPPERCASE (e.g. CHEN, WANG, LUTZ)
  - Given name tokens have mixed case (e.g. Meng, Amy, I-Ching)
  - Surname must come first

normalize_player_name() detects the order by casing and reorders if needed.
It also handles the "NAME (COUNTRY_CODE)" format used in match records.
"""
from __future__ import annotations

import re

# Optional trailing country code, e.g. " (CHN)" or " (USA)"
_COUNTRY_CODE_RE = re.compile(r"(\s*\([A-Z]{3}\))\s*$")


def normalize_player_name(name: str) -> str:
    """Return name in canonical SURNAME Given_name order.

    Surname tokens are identified by str.isupper() (all cased characters are
    uppercase).  If the given-name part precedes the surname part the tokens
    are reordered; otherwise the name is returned unchanged.

    Handles embedded country codes like "Amy WANG (USA)" transparently.

    Examples::

        normalize_player_name("Amy WANG")          -> "WANG Amy"
        normalize_player_name("Amy WANG (USA)")    -> "WANG Amy (USA)"
        normalize_player_name("CHEN Meng")         -> "CHEN Meng"
        normalize_player_name("CHENG I-Ching")     -> "CHENG I-Ching"
        normalize_player_name("DOO Hoi Kem")       -> "DOO Hoi Kem"
        normalize_player_name("Charlotte LUTZ")    -> "LUTZ Charlotte"
    """
    if not name:
        return name

    # Strip and save optional country code suffix
    country_suffix = ""
    m = _COUNTRY_CODE_RE.search(name)
    if m:
        country_suffix = m.group(1)
        name = name[: m.start()].strip()

    tokens = name.split()
    if len(tokens) <= 1:
        return name + country_suffix

    surname_indices = [i for i, t in enumerate(tokens) if t.isupper()]
    given_indices = [i for i, t in enumerate(tokens) if not t.isupper()]

    # Cannot distinguish order when all tokens share the same casing
    if not surname_indices or not given_indices:
        return name + country_suffix

    # If surname already leads, nothing to do
    if surname_indices[0] < given_indices[0]:
        return name + country_suffix

    # Reorder: preserve relative order within each group
    surname_tokens = [tokens[i] for i in surname_indices]
    given_tokens = [tokens[i] for i in given_indices]
    return " ".join(surname_tokens + given_tokens) + country_suffix
