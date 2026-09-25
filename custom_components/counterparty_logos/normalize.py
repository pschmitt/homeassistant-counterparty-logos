"""Turn raw bank statement counterparty names into brand search queries."""

from __future__ import annotations

import re
import unicodedata

# Card scheme prefix, optionally followed by a terminal/card number:
# "VISA EDEKA 2143", "VISA 2112 LEVY RESTAURANTS".
_CARD_PREFIX = re.compile(
    r"^(?:visa|mastercard|maestro|girocard|ec)\s+(?:\d{3,5}\s+)?", re.IGNORECASE
)
# Payment processor prefix in front of the actual merchant:
# "SumUp *Gandzior", "PAYPAL *SMARTDOMO", "Klarna*reichelt.com".
_PROCESSOR_PREFIX = re.compile(
    r"^(?:sumup|sp|sq|paypal|klarna|zettle|iz|pp|lsp)\s*\*\s*", re.IGNORECASE
)
_DOMAIN = re.compile(
    r"\b((?:[a-z0-9-]+\.)+(?:com|de|eu|net|org|io|ai|app|dev|fr|nl|at|ch|it|es|co\.uk|shop|store))\b",
    re.IGNORECASE,
)
_NOISE_WORDS = re.compile(
    r"\b(?:"
    # legal forms
    r"gmbh|ag|aktiengesell\w*|limited|ltd|b\.?v|s\.?a\.?r\.?l|et cie|s\.?c\.?a|co|ohg|kg"
    r"|zrt|inc|se|llc|plc|sa|spa|foundation"
    # regional subsidiaries
    r"|germany|deutschland|europe|international|ireland"
    r")\b\.?",
    re.IGNORECASE,
)
_TOKEN_WITH_DIGIT = re.compile(r"\b\w*\d\w*\b")
_PARENTHESIZED = re.compile(r"\([^)]*\)")
_PUNCTUATION = re.compile(r"[*.+,/&|]+")
_WHITESPACE = re.compile(r"\s+")
_TLD_SUFFIX = re.compile(r"\.(?:com|de|net|org|io|ai|co\.uk)$", re.IGNORECASE)


def strip_prefixes(name: str) -> str:
    """Remove card scheme and payment processor prefixes."""
    name = _CARD_PREFIX.sub("", name.strip())
    return _PROCESSOR_PREFIX.sub("", name).strip()


def extract_domain(name: str) -> str | None:
    """Return a domain embedded in the name, e.g. "Klarna*reichelt.com"."""
    match = _DOMAIN.search(strip_prefixes(name))
    if match is None:
        return None
    domain = match.group(1).lower()
    return domain.removeprefix("www.")


def search_query(name: str) -> str:
    """Reduce a raw counterparty name to a brand name suitable for searching."""
    query = strip_prefixes(name)
    query = re.sub(r"^www\.", "", query, flags=re.IGNORECASE)
    query = _PARENTHESIZED.sub(" ", query)
    query = _NOISE_WORDS.sub(" ", query)
    query = _TOKEN_WITH_DIGIT.sub(" ", query)
    query = _PUNCTUATION.sub(" ", query)
    return _WHITESPACE.sub(" ", query).strip(" -")


def fold(text: str) -> str:
    """Lowercase and strip accents, keeping word boundaries."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return _WHITESPACE.sub(" ", re.sub(r"[^a-z0-9]+", " ", stripped.lower())).strip()


def match_key(text: str) -> str:
    """Return a compact comparison key: folded, without spaces."""
    return fold(text).replace(" ", "")


def brand_name_key(name: str) -> str:
    """Comparison key for a search result name ("Namecheap.com" -> "namecheap")."""
    return match_key(_NOISE_WORDS.sub(" ", _TLD_SUFFIX.sub("", name.strip())))


def domain_label_key(domain: str) -> str:
    """Comparison key for a domain's leading label ("www.g-pay.vn" -> "gpay")."""
    return match_key(domain.lower().removeprefix("www.").split(".", 1)[0])
