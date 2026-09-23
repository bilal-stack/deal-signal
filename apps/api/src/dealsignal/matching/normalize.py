"""Turning messy source values into comparable ones.

Every function here is pure and side-effect free: same input, same output, no
network, no database. That is what makes the duplicate matcher testable.
"""

from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlparse

import phonenumbers
import tldextract
from phonenumbers import NumberParseException

LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "company",
        "plc",
        "lp",
        "llp",
        "pllc",
        "pc",
        "gmbh",
        "sarl",
        "sas",
        "sa",
        "sasu",
        "eurl",
        "sci",
        "group",
        "holdings",
        "holding",
        "the",
    }
)
"""Words that say nothing about which business this is."""

_PUNCTUATION = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WHITESPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Reduce a company name to the part that identifies it.

    >>> normalize_name("Craddock Lumber Co., LLC")
    'craddock lumber'
    """
    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode()
    folded = _PUNCTUATION.sub(" ", folded.lower())
    words = [word for word in _WHITESPACE.split(folded) if word and word not in LEGAL_SUFFIXES]
    return " ".join(words)


def compact_name(raw: str) -> str:
    """The name as one run of letters and digits, without "and" or legal suffixes.

    >>> compact_name("Ray's A/C & Heating Services.")
    'raysacheatingservices'
    >>> compact_name("Rays AC and Heating Services")
    'raysacheatingservices'
    """
    return "".join(word for word in normalize_name(raw).split() if word != "and")


def website_path(raw: str | None) -> str:
    """The page a listing points at on its website, "" for the home page.

    >>> website_path("https://www.aireserv.com/ft-worth/?cid=LSTL")
    'ft-worth'
    """
    if not raw:
        return ""
    return urlparse(raw.strip()).path.strip("/").lower()


def normalize_domain(raw: str | None) -> str | None:
    """Reduce a URL or host to its registrable domain, lowercase.

    >>> normalize_domain("https://WWW.Dallasdoor.com/contact?x=1")
    'dallasdoor.com'
    """
    if not raw:
        return None
    extracted = tldextract.extract(raw.strip())
    if not extracted.domain or not extracted.suffix:
        return None
    return f"{extracted.domain}.{extracted.suffix}".lower()


def normalize_phone(raw: str | None, *, country: str) -> str | None:
    """Convert a phone number to E.164, or return None if it is not valid.

    An unparseable number is not an error worth raising: it is simply not a phone
    number we can trust, and the field stays empty with a reason.
    """
    if not raw:
        return None
    try:
        parsed = phonenumbers.parse(raw, country)
    except NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
