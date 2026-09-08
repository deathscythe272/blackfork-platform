"""Redaction before storage (ADR-006). Free text is scanned for personal data and each
hit is replaced with a typed placeholder before the row reaches silver, so nothing
downstream, agents included, can carry what silver does not hold.

Presidio does the finding: pattern recognizers for addresses and numbers, a language
model for names. The entity set is deliberate and short; a wider net would redact the
control names and system ids the platform runs on. Serves: BR-7, C2.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

ENTITIES = ["PERSON", "EMAIL_ADDRESS", "IP_ADDRESS", "PHONE_NUMBER"]

# The platform's own vocabulary, never redacted. The language model read "Suricata",
# the sensor engine named at the start of a summary, as a person and erased it from two
# evidence rows on the first full scan; every name here was added because a row showed
# the need, per ADR-006, and each carries the row that proved it.
ALLOW_LIST = [
    "Suricata",         # ev-0004, ev-0103: the sensor engine that raised the alert
    "Security Onion",
    "Nmap", "Trivy", "Grype", "Terraform", "Dagster", "SIEM", "Windrow", "Blackfork",
]
PLACEHOLDERS = {"PERSON": "<PERSON>", "EMAIL_ADDRESS": "<EMAIL>", "IP_ADDRESS": "<IP>", "PHONE_NUMBER": "<PHONE>"}
MIN_SCORE = 0.4  # below this the language model is guessing; the check below catches what slips


@dataclass
class Redaction:
    text: str
    entities: list[str] = field(default_factory=list)  # entity types found, one per hit


@functools.lru_cache(maxsize=1)
def _engines() -> tuple[AnalyzerEngine, AnonymizerEngine]:
    return AnalyzerEngine(), AnonymizerEngine()


def find(text: str) -> list[str]:
    """Entity types present in `text`, one per hit. Empty means clean."""
    if not text:
        return []
    analyzer, _ = _engines()
    return [r.entity_type for r in analyzer.analyze(text=text, language="en", entities=ENTITIES, score_threshold=MIN_SCORE, allow_list=ALLOW_LIST)]


def redact(text: str) -> Redaction:
    if not text:
        return Redaction(text or "")
    analyzer, anonymizer = _engines()
    results = analyzer.analyze(text=text, language="en", entities=ENTITIES, score_threshold=MIN_SCORE, allow_list=ALLOW_LIST)
    if not results:
        return Redaction(text)
    operators = {k: OperatorConfig("replace", {"new_value": v}) for k, v in PLACEHOLDERS.items()}
    out = anonymizer.anonymize(text=text, analyzer_results=results, operators=operators)
    return Redaction(out.text, [r.entity_type for r in results])


# An independent second look for the silver check. Plain patterns, no language model:
# if the redactor's detector goes blind, this layer does not go blind with it.
_PATTERNS = {
    "EMAIL_ADDRESS": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "PHONE_NUMBER": re.compile(r"(?:\+\d{1,3}[\s-])?\(?\d{3}\)?[\s-]\d{3}[\s-]\d{4}\b"),
}


def find_patterns(text: str) -> list[str]:
    """Entity types matched by plain patterns, sorted; empty means clean."""
    if not text:
        return []
    return sorted(kind for kind, rx in _PATTERNS.items() for _ in rx.finditer(text))
