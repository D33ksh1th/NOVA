"""Deterministic lexical relevance, not a probability or truth assessment."""

import re
import unicodedata


IGNORED = frozenset({"a", "an", "and", "are", "about", "for", "from", "in", "is", "of", "on", "or", "the",
                     "to", "with", "what", "who", "how", "search", "find", "information", "please", "me", "tell"})


def words(text: str) -> list[str]:
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def relevance_score(query: str, title: str, snippet: str = "") -> dict:
    terms = set(words(query)) - IGNORED
    title_terms, body_terms = set(words(title)), set(words(snippet))
    matched = terms & (title_terms | body_terms)
    missing = terms - matched
    normalized = " " + " ".join(words(title + " " + snippet)) + " "
    phrases = [" ".join(words(phrase)) for phrase in re.findall(r'"([^"\n]+)"', query)]
    phrase_match = all(f" {phrase} " in normalized for phrase in phrases if phrase)
    ordered = [term for term in words(query) if term not in IGNORED]
    exact = bool(ordered) and f" {' '.join(ordered)} " in normalized
    score = (60 * len(matched) / len(terms) + 25 * len(terms & title_terms) / len(terms)
             + 15 * exact) if terms else 0
    if not phrase_match:
        score = 0
    if any(term.isdecimal() for term in missing):
        score = min(score, 35)
    return {"score": round(score), "matched_terms": sorted(matched), "missing_terms": sorted(missing),
            "method": "lexical-v1", "query": query}