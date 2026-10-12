"""
PROJECT: Datacom Kudos System
FILE: src/services/ai_moderation.py
DESCRIPTION: Automated AI Heuristic Content Moderation and Smart Triage Engine
             Implements deterministic text normalization, toxicity/spam scoring,
             and a resilient Fail-Open fallback policy.
"""

import re
import unicodedata
import logging
from typing import Tuple, Optional

# Structured logger for AI content analysis
logger = logging.getLogger("ai_moderation")

# Bilingual (English/French) dictionary of inappropriate and offensive terms
OFFENSIVE_TERMS = {
    # English terms
    "idiot", "stupid", "incompetent", "lazy", "useless", "moron", "hate", "trash",
    "dumb", "fool", "loser", "shut up", "disgusting", "pathetic",
    # French terms
    "nul", "idiot", "imbecile", "incompetent", "faineant", "dechet", "degage",
    "stupide", "merde", "connard", "salaud", "ferme la", "pourri"
}

# Common leetspeak substitutions to prevent evasion
LEET_TRANSLATIONS = str.maketrans({
    "@": "a", "4": "a",
    "3": "e",
    "1": "i",
    "0": "o",
    "5": "s", "$": "s",
    "7": "t", "+": "t"
})


def normalize_text(text: str) -> str:
    """
    Normalizes input text for heuristic evaluation:
    1. Converts to lowercase
    2. Strips diacritics / accents (e.g., 'é' -> 'e')
    3. Translates leetspeak characters
    4. Reduces multiple consecutive spaces
    """
    if not text:
        return ""

    # Convert to lowercase
    normalized = text.lower()

    # Translate leetspeak numbers/symbols to letters
    normalized = normalized.translate(LEET_TRANSLATIONS)

    # Decompose unicode characters and strip accents
    normalized = "".join(
        c for c in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(c) != "Mn"
    )

    # Collapse multiple whitespaces
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def detect_repeated_character_spam(text: str, threshold: int = 5) -> bool:
    """
    Detects spam-like repeated characters (e.g., 'aaaaaaa' or '!!!!!!!').
    """
    pattern = rf"(.)\1{{{threshold},}}"
    return bool(re.search(pattern, text))


def detect_external_links(text: str) -> bool:
    """
    Detects external URLs or phishing links.
    """
    url_pattern = r"(https?://|www\.)[^\s]+"
    return bool(re.search(url_pattern, text, re.IGNORECASE))


def evaluate_content(message: str) -> Tuple[bool, Optional[str]]:
    """
    Synchronously evaluates kudo message content against heuristic rules.
    Returns:
        (ai_flagged: bool, ai_flag_reason: Optional[str])

    Resilience Policy (Fail-Open):
        If an unhandled exception occurs inside this module, the message
        is published normally (ai_flagged=False) and an ERROR is logged.
    """
    try:
        if not message or not message.strip():
            return False, None

        normalized = normalize_text(message)

        # 1. Check for offensive vocabulary
        words = re.findall(r"\b\w+\b", normalized)
        for word in words:
            if word in OFFENSIVE_TERMS:
                logger.warning(f"[AI_FLAG] Offensive keyword detected: '{word}'")
                return True, f"AI Alert: Inappropriate language detected ('{word}')"

        # 2. Check for multi-word offensive phrases
        for phrase in ["shut up", "ferme la", "work like a slave"]:
            if phrase in normalized:
                logger.warning(f"[AI_FLAG] Inappropriate phrase detected: '{phrase}'")
                return True, f"AI Alert: Inappropriate phrase detected ('{phrase}')"

        # 3. Check for repetitive character spam
        if detect_repeated_character_spam(message):
            logger.warning("[AI_FLAG] Repetitive character spam detected")
            return True, "AI Alert: Repetitive character pattern detected"

        # 4. Check for external links
        if detect_external_links(message):
            logger.warning("[AI_FLAG] External URL detected")
            return True, "AI Alert: External link detected (potential spam)"

        # Content is clean
        return False, None

    except Exception as exc:
        # FAIL-OPEN POLICY: Do not block legitimate users if the heuristic engine encounters a fault
        logger.error(
            f"[AI_FAIL_OPEN] Error during heuristic evaluation: {exc}. "
            "Applying Fail-Open policy (message allowed through without flag).",
            exc_info=True
        )
        return False, None
