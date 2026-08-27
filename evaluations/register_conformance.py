#!/usr/bin/env python3
"""Register-conformance scoring for the `-wesh` model variant (ADR-0526).

ADR-0526 decision 8: promotion requires BOTH halves of the gate. The
existing ADR-0027/ADR-0028 acceptance suite is the substance half - it is
entirely tone-blind by construction (status codes, JSON fields,
non-emptiness, latency, SSE framing; no semantic judge anywhere), which is
exactly what makes it a clean control. This module is the style half, and
it is the ONLY thing here that looks at how an answer is written.

Both halves are mandatory. A model that adopts the register while losing
factual accuracy is a failed candidate, not a stylistic success - the
corpus says so itself, in rule 14 ("Facts and reasoning must remain
correct: style changes, information quality does not") and rule 20
("parler différemment sans raisonner différemment").

WHY THIS IS NOT A SET OF SCENARIOS. Adding N register scenarios to
evaluations/<agent>/scenarios.yaml would put them in the ADR-0028
DENOMINATOR: with 20 existing scenarios, 3 added and all 3 failing still
scores 20/23 = 87% >= 75% and reports PASS. That does not implement
decision 8. The register half is therefore computed independently and
AND-ed with the acceptance result, so either half failing fails the run.

Stdlib only, and deliberately so - two callers import the same function:
components/mlops's `evaluate` stage (which must not acquire httpx and a
module-level URL/env setup it has no use for) and
evaluations/tekos/run_scenarios.py's live handler.

THRESHOLDS ARE DATA, not code (ADR-0107's own principle): they live in
evaluations/<agent>/gate_config.yaml alongside scenario_threshold. The
defaults below are calibrated against the reference corpus itself
(2026-08-27, s3://zuno-corpus/qwen-wesh-training-corpus.tgz), not guessed:

    marker rate      test 86.1% / validation 85.0% / train 89.4%
    distinct markers 21 in the 79-response test split alone
    response length  min 43 chars, median ~163
    rule 3           5.9% of reference answers open with "wesh"
    rule 17          mean marker density 0.064/word, p95 0.250

so a floor of 0.70 sits ~15 points below the reference (loose enough not
to fail a slightly-weaker fine-tune, tight enough that a no-op merge
scoring ~0 can never be confused with a good one), and the ceilings sit
far above normal usage while still catching degenerate saturation.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence

# --- vocabulary ---------------------------------------------------------
# Transcribed from the corpus README's own rules. Accent-stripped and
# lowercased, because _normalize does the same to the text being scored -
# so "frérot" and "frerot", "carré" and "carre", all match one entry.
#
# rule 2  - register markers
# rule 9  - contemporary slang
# rule 10 - address terms
# rule 21 - SMS abbreviations
_SINGLE_WORD_MARKERS = frozenset("""
wesh franchement bah tranquille grave sah tema
carre propre lourd chelou relou galere dinguerie bail chaud charbonner
matrixe rince refait frappe masterclass
frerot frere reuf mif
slt bjr cv mrc stp pk pcq bcp tjs trkl tkt vrmt
""".split())

# Multi-word markers (rules 2, 7, 8, 10) and rule 4's spoken contractions.
# Ordered longest-first so "mon reuf" is not shadowed by "reuf".
_PHRASE_MARKERS = (
    "mon reuf", "le sang", "la mif", "en vrai", "en gros", "vas-y", "de ouf",
    "j'sais pas", "j'suis", "j'vais", "c'est pas", "j'te", "t'as", "y a",
)

MARKERS = _SINGLE_WORD_MARKERS
_WORD_RE = re.compile(r"[\w'-]+", re.UNICODE)
_PHRASE_RES = tuple((p, re.compile(re.escape(p))) for p in _PHRASE_MARKERS)


def _env_markers() -> frozenset:
    """ZUNO_REGISTER_MARKERS overrides the built-in vocabulary.

    The corpus is a tarball in S3 that nothing in this repository reads at
    runtime, and the live scenario handler has no S3 access at all - so the
    vocabulary is transcribed here rather than parsed. This escape hatch
    means a corpus revision is a config change, not a code change.
    """
    raw = os.getenv("ZUNO_REGISTER_MARKERS", "").strip()
    if not raw:
        return _SINGLE_WORD_MARKERS
    return frozenset(_normalize(t) for t in raw.split(",") if t.strip())


def _normalize(text: str) -> str:
    """Lowercase and strip combining accents. Matching normalized text
    against a normalized vocabulary is what lets a model write "frérot" or
    "frerot" and score identically - a fine-tune's accent handling is not
    what this gate is measuring."""
    lowered = text.lower()
    return "".join(c for c in unicodedata.normalize("NFD", lowered) if unicodedata.category(c) != "Mn")


# --- rules 11-13: protected spans --------------------------------------
# "Never replace precise technical terminology with ambiguous slang",
# "keep product names, protocols, APIs, commands and technical concepts
# exact", "never slangify code/YAML/JSON/SQL/shell syntax".
#
# Detected as SPANS rather than as a blocklist of words: the question is
# not whether a technical term appears, it is whether a register marker
# appears INSIDE one. That is the only thing rules 11-13 actually forbid.
# CALIBRATED AGAINST THE REFERENCE CORPUS, not written from intuition. A
# first version treated any line beginning with a tool name (git, make,
# oc, kubectl...) as a shell command, and the corpus immediately produced
# three false positives - "git garde l'historique de ton code... c'est le
# sang" is a French sentence whose SUBJECT is git, not a command line, and
# `[^\n]*` swallowed the whole sentence including its markers. A gate that
# fails a perfectly correct answer is worse than no gate: it would block a
# valid promotion and teach everyone to bypass it.
#
# So bare-text detection is kept ONLY where the pattern is unambiguous in
# French prose. Shell and YAML must be DELIMITED - by a fence, by
# backticks, by a `$`/`#!` prefix, or (for YAML) by indentation, which is
# what actually distinguishes structure from a sentence containing a
# colon. That is not a loss of coverage: rules 11-13 protect SYNTAX, and
# syntax quoted inside prose is delimited by convention.
_PROTECTED_PATTERNS = (
    ("fenced-code", re.compile(r"```.*?```", re.S)),
    ("inline-code", re.compile(r"`[^`\n]+`")),
    # Real command markers only: a prompt sigil or a shebang.
    ("shell", re.compile(r"^[ \t]*(?:\$|#!)[^\n]*", re.M)),
    # INDENTED key: value. A top-level "Historique: ..." in French prose is
    # a sentence; an indented one is structure.
    ("yaml", re.compile(r"^[ \t]+[A-Za-z_][\w.-]*:\s+\S[^\n]*", re.M)),
    ("json", re.compile(r"[{\[][^{}\[\]\n]*[}\]]")),
    # Uppercase only - lowercase "select"/"update" are ordinary French or
    # English words, and case is what makes this unambiguous.
    ("sql", re.compile(r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b[^\n]*")),
    ("dotted-identifier", re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w+)+\b")),
    ("acronym", re.compile(r"\b[A-Z][A-Z0-9]{2,}\b")),
    ("camel-case", re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b")),
)


def protected_spans(text: str) -> List[Dict[str, Any]]:
    spans: List[Dict[str, Any]] = []
    for kind, pattern in _PROTECTED_PATTERNS:
        for m in pattern.finditer(text):
            spans.append({"kind": kind, "start": m.start(), "end": m.end(), "text": m.group(0)})
    return spans


def _in_any(pos: int, end: int, spans: Sequence[Dict[str, Any]]) -> Dict[str, Any] | None:
    for s in spans:
        if pos >= s["start"] and end <= s["end"]:
            return s
    return None


def score_text(text: str, *, markers: frozenset | None = None) -> Dict[str, Any]:
    """Scores one response. Returns the markers found, their density, and
    any rule 11-13 violation (a marker inside a protected span)."""
    vocab = markers if markers is not None else _env_markers()
    norm = _normalize(text)
    spans = protected_spans(text)

    found: Dict[str, int] = {}
    violations: List[Dict[str, Any]] = []

    for m in _WORD_RE.finditer(norm):
        if m.group(0) not in vocab:
            continue
        found[m.group(0)] = found.get(m.group(0), 0) + 1
        hit = _in_any(m.start(), m.end(), spans)
        if hit:
            violations.append({"marker": m.group(0), "kind": hit["kind"], "span": hit["text"][:120]})
    for phrase, rx in _PHRASE_RES:
        for m in rx.finditer(norm):
            found[phrase] = found.get(phrase, 0) + 1
            hit = _in_any(m.start(), m.end(), spans)
            if hit:
                violations.append({"marker": phrase, "kind": hit["kind"], "span": hit["text"][:120]})

    words = len(_WORD_RE.findall(norm)) or 1
    total = sum(found.values())
    return {
        "markers": sorted(found),
        "marker_count": total,
        "density": total / words,
        "word_count": words,
        "char_count": len(text),
        "opens_with_marker": next((k for k in ("wesh",) if norm.lstrip().startswith(k)), None),
        "violations": violations,
    }


def score_corpus(
    completions: Iterable[str],
    *,
    marker_rate_threshold: float = 0.70,
    min_distinct_markers: int = 5,
    min_response_chars: int = 20,
    max_opening_marker_rate: float = 0.30,
    max_mean_density: float = 0.30,
) -> Dict[str, Any]:
    """Scores a whole set of completions and decides PASS/FAIL.

    Five independent conditions, all of which must hold. The last two are
    CEILINGS, and they exist because the corpus's own rules impose them -
    a naive "more markers is better" scorer would reward exactly the
    degenerate model rules 3 and 17 forbid:

      floor    marker rate            >= marker_rate_threshold   (rules 2, 9)
      floor    distinct markers used  >= min_distinct_markers    (anti-degeneracy)
      floor    every response length  >= min_response_chars      (anti-degeneracy)
      CEILING  responses opening "wesh" <= max_opening_marker_rate (rule 3)
      CEILING  mean marker density    <= max_mean_density        (rule 17)

    plus a MANDATORY negative check: any rule 11-13 violation fails the
    whole set regardless of every number above, mirroring the way the
    acceptance gate's security checks are non-skippable. A model that
    slangifies a YAML key or an API name has broken the one thing the
    register shift was never allowed to touch.
    """
    vocab = _env_markers()
    scored = [score_text(c, markers=vocab) for c in completions]
    if not scored:
        return {"passed": False, "reason": "no completions to score", "sample_count": 0}

    n = len(scored)
    with_marker = sum(1 for s in scored if s["marker_count"] > 0)
    marker_rate = with_marker / n
    distinct = sorted({m for s in scored for m in s["markers"]})
    short = [s for s in scored if s["char_count"] < min_response_chars]
    opening = sum(1 for s in scored if s["opens_with_marker"]) / n
    mean_density = sum(s["density"] for s in scored) / n
    violations = [v for s in scored for v in s["violations"]]

    failures: List[str] = []
    if marker_rate < marker_rate_threshold:
        failures.append(f"marker rate {marker_rate:.1%} < {marker_rate_threshold:.1%} (rules 2/9)")
    if len(distinct) < min_distinct_markers:
        failures.append(f"only {len(distinct)} distinct markers < {min_distinct_markers} (degenerate)")
    if short:
        failures.append(f"{len(short)} responses shorter than {min_response_chars} chars (degenerate)")
    if opening > max_opening_marker_rate:
        failures.append(f"{opening:.1%} of answers open with 'wesh' > {max_opening_marker_rate:.1%} (rule 3)")
    if mean_density > max_mean_density:
        failures.append(f"mean marker density {mean_density:.3f} > {max_mean_density:.3f} (rule 17)")
    if violations:
        failures.append(
            f"{len(violations)} register markers inside protected technical spans (rules 11-13): "
            + "; ".join(f"{v['marker']} in {v['kind']}" for v in violations[:5])
        )

    return {
        "passed": not failures,
        "sample_count": n,
        "marker_rate": round(marker_rate, 4),
        "distinct_markers": distinct,
        "distinct_marker_count": len(distinct),
        "mean_density": round(mean_density, 4),
        "opening_marker_rate": round(opening, 4),
        "violations": violations[:20],
        "violation_count": len(violations),
        "failures": failures,
    }


def thresholds_from_gate_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Reads this module's knobs out of an agent's gate_config.yaml,
    falling back to the calibrated defaults. quality_gate.load_gate_config
    already returns the whole dict, so the acceptance gate needs no change
    and its own scenario_threshold is untouched."""
    return {
        "marker_rate_threshold": float(config.get("register_marker_rate_threshold", 0.70)),
        "min_distinct_markers": int(config.get("register_min_distinct_markers", 5)),
        "min_response_chars": int(config.get("register_min_response_chars", 20)),
        "max_opening_marker_rate": float(config.get("register_max_opening_marker_rate", 0.30)),
        "max_mean_density": float(config.get("register_max_mean_density", 0.30)),
    }
