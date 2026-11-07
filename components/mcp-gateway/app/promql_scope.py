"""ADR-0603 M13 (WP-225 lot B): a namespace matcher enforced in every PromQL selector.

`metrics.query` reaches kubernetes-mcp-server's `execute_instant_query`, which asks
the Thanos Querier with a ServiceAccount that has cluster-monitoring-view: it reads
the metrics of every namespace. The server only requires some label matcher. This
module makes the gateway restrict the query, before it leaves, to the namespaces
the caller's groups are entitled to (`METRICS_NAMESPACES_BY_GROUP`).

How the matcher is enforced, and why a crafted query cannot escape it:

- The query is tokenised with PromQL's own lexical rules (strings with their three
  quote styles and escapes, comments, numbers, durations, identifiers, operators).
  A character or a token PromQL would not accept is a refusal, not a guess.
- Every vector selector gets `namespace=~"<allowed>"` added to its matcher list: a
  bare metric name (`up` becomes `up{namespace=~"a|b"}`), a selector with matchers,
  and a selector without a name (`{__name__=~".+"}`). Matchers of one selector are
  ANDed by Prometheus, so a caller's own `namespace` matcher (`=~".*"`, `!=`, a
  second `namespace=`) can only narrow the result further, never widen it.
- A Prometheus 3 `or` inside braces makes alternatives; the matcher is added to each
  alternative, so `{a="1" or b="2"}` cannot carry one unscoped half.
- Label lists (`by`, `without`, `on`, `ignoring`, `group_left`, `group_right`), the
  range and subquery brackets, strings and function names are never touched: they
  select no series.
- `info()` is refused: it reads `target_info` series that the query does not name.

The result is a query in which no series can be selected outside the allowed
namespaces. A metric without a `namespace` label (node or cluster-level series)
selects nothing, which is the intended consequence.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence

logger = logging.getLogger("mcp_gateway.promql_scope")

NAMESPACE_LABEL = "namespace"
WILDCARD = "*"

# A Kubernetes namespace name (RFC 1123 label). Validated on the configuration, so the
# regular expression built from it needs no escaping.
_NAMESPACE_RE = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")

_KEYWORDS = {
    "and", "or", "unless", "atan2", "bool", "offset", "by", "without", "on", "ignoring",
    "group_left", "group_right",
}
_LABEL_LIST_KEYWORDS = {"by", "without", "on", "ignoring", "group_left", "group_right"}
# Aggregation operators are keywords in PromQL, never metric names, including when the
# label list comes first (`sum by (le) (...)`).
_AGGREGATIONS = {
    "sum", "min", "max", "avg", "group", "stddev", "stdvar", "count", "count_values", "bottomk", "topk",
    "quantile", "limitk", "limit_ratio",
}
_NUMBER_WORDS = {"inf", "nan"}
_REFUSED_FUNCTIONS = {"info"}

_IDENT_RE = re.compile(r"[A-Za-z_:][A-Za-z0-9_:]*")
_NUMBERISH_RE = re.compile(r"[0-9.][0-9A-Za-z_.]*")
_NUMBER_RE = re.compile(
    r"0[xX][0-9a-fA-F]+|(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?"
)
_DURATION_RE = re.compile(r"(?:[0-9]+(?:ms|[smhdwy]))+")
_OPERATORS = ("==", "!=", "<=", ">=", "=~", "!~", "+", "-", "*", "/", "%", "^", "<", ">", "=")
_PUNCTUATION = "{}()[],:@"
# ASCII only: str.isdigit()/isspace() also accept "²" or U+2003, which PromQL does
# not, and which no regular expression below would match.
_DIGITS = frozenset("0123456789")
_SPACES = frozenset(" \t\n\r\f\v")


class PromQLScopeError(ValueError):
    """The query cannot be scoped (malformed, or uses a refused construct)."""


@dataclass
class _Token:
    kind: str  # ws, comment, string, number, ident, op, punct
    text: str


def _tokenize(query: str) -> List[_Token]:
    tokens: List[_Token] = []
    i, n = 0, len(query)
    bracket_depth = 0
    while i < n:
        ch = query[i]
        if ch in _SPACES:
            j = i
            while j < n and query[j] in _SPACES:
                j += 1
            tokens.append(_Token("ws", query[i:j]))
            i = j
            continue
        if ch == "#":
            j = query.find("\n", i)
            j = n if j < 0 else j
            tokens.append(_Token("comment", query[i:j]))
            i = j
            continue
        if ch in ('"', "'"):
            j = i + 1
            while j < n and query[j] != ch:
                if query[j] == "\\":
                    j += 1
                if query[j:j + 1] == "\n":
                    raise PromQLScopeError("a newline inside a quoted string")
                j += 1
            if j >= n:
                raise PromQLScopeError("an unterminated string")
            tokens.append(_Token("string", query[i:j + 1]))
            i = j + 1
            continue
        if ch == "`":
            j = query.find("`", i + 1)
            if j < 0:
                raise PromQLScopeError("an unterminated raw string")
            tokens.append(_Token("string", query[i:j + 1]))
            i = j + 1
            continue
        if ch in _DIGITS or (ch == "." and i + 1 < n and query[i + 1] in _DIGITS):
            m = _NUMBERISH_RE.match(query, i)
            if m is None:
                raise PromQLScopeError(f"bad number at offset {i}")
            text = m.group(0)
            if not (_NUMBER_RE.fullmatch(text) or _DURATION_RE.fullmatch(text)):
                raise PromQLScopeError(f"bad number or duration {text!r}")
            tokens.append(_Token("number", text))
            i = m.end()
            continue
        if ch == ":" and bracket_depth > 0:
            # The subquery colon (`[5m:1m]`); outside brackets `:` may start a metric name.
            tokens.append(_Token("punct", ch))
            i += 1
            continue
        m = _IDENT_RE.match(query, i)
        if m:
            tokens.append(_Token("ident", m.group(0)))
            i = m.end()
            continue
        op = next((o for o in _OPERATORS if query.startswith(o, i)), None)
        if op:
            tokens.append(_Token("op", op))
            i += len(op)
            continue
        if ch in _PUNCTUATION:
            if ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth = max(0, bracket_depth - 1)
            tokens.append(_Token("punct", ch))
            i += 1
            continue
        raise PromQLScopeError(f"unexpected character {ch!r} at offset {i}")
    return tokens


def _next_significant(tokens: Sequence[_Token], start: int) -> int:
    j = start
    while j < len(tokens) and tokens[j].kind in ("ws", "comment"):
        j += 1
    return j


def _matching(tokens: Sequence[_Token], start: int, open_ch: str, close_ch: str) -> int:
    depth = 0
    for j in range(start, len(tokens)):
        tok = tokens[j]
        if tok.kind != "punct":
            continue
        if tok.text == open_ch:
            depth += 1
        elif tok.text == close_ch:
            depth -= 1
            if depth == 0:
                return j
    raise PromQLScopeError(f"unbalanced {open_ch!r}")


def _scoped_matchers(tokens: Sequence[_Token], matcher: str) -> str:
    """The inside of one `{...}`, with `matcher` added at the end of each alternative."""
    out: List[str] = []
    last_significant: Optional[_Token] = None

    def close_alternative() -> None:
        if last_significant is None or (last_significant.kind == "punct" and last_significant.text == ","):
            out.append(matcher)
        else:
            out.append(", " + matcher)

    for tok in tokens:
        if tok.kind == "punct" and tok.text in "{}()[]":
            raise PromQLScopeError("a bracket inside a label matcher list")
        if tok.kind == "number":
            raise PromQLScopeError("a number inside a label matcher list")
        if tok.kind == "ident" and tok.text.lower() == "or":
            close_alternative()
            out.append(" or ")
            last_significant = None
            continue
        if tok.kind == "comment":
            out.append("\n")
            continue
        out.append(tok.text)
        if tok.kind != "ws":
            last_significant = tok
    close_alternative()
    return "".join(out)


def scope_query(query: str, namespaces: Sequence[str]) -> str:
    """`query` with a `namespace=~"<namespaces>"` matcher in every vector selector."""
    if not isinstance(query, str) or not query.strip():
        raise PromQLScopeError("the query is empty")
    allowed = sorted(set(namespaces))
    if not allowed:
        raise PromQLScopeError("no namespace is allowed")
    for ns in allowed:
        if not _NAMESPACE_RE.fullmatch(ns):
            raise PromQLScopeError(f"invalid namespace {ns!r} in the configuration")
    matcher = f'{NAMESPACE_LABEL}=~"{"|".join(allowed)}"'

    tokens = _tokenize(query)
    out: List[str] = []
    i = 0
    selectors = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.kind == "comment":
            out.append("\n")
            i += 1
            continue
        if tok.kind == "punct" and tok.text == "}":
            raise PromQLScopeError("unbalanced '}'")
        if tok.kind == "punct" and tok.text == "[":
            end = _matching(tokens, i, "[", "]")
            inner = tokens[i + 1:end]
            if any(not (t.kind in ("ws", "number", "op") or (t.kind == "punct" and t.text == ":")) for t in inner):
                raise PromQLScopeError("a range or subquery bracket may hold durations only")
            out.extend(t.text for t in tokens[i:end + 1])
            i = end + 1
            continue
        if tok.kind == "punct" and tok.text == "{":
            end = _matching(tokens, i, "{", "}")
            out.append("{" + _scoped_matchers(tokens[i + 1:end], matcher) + "}")
            selectors += 1
            i = end + 1
            continue
        if tok.kind == "ident":
            word = tok.text
            nxt = _next_significant(tokens, i + 1)
            nxt_tok = tokens[nxt] if nxt < len(tokens) else None
            followed_by_paren = nxt_tok is not None and nxt_tok.kind == "punct" and nxt_tok.text == "("
            lower = word.lower()
            if lower in _LABEL_LIST_KEYWORDS and followed_by_paren:
                end = _matching(tokens, nxt, "(", ")")
                inner = tokens[nxt + 1:end]
                if any(t.kind not in ("ws", "ident", "string") and not (t.kind == "punct" and t.text == ",") for t in inner):
                    raise PromQLScopeError(f"the label list of '{word}' may hold label names only")
                out.extend(t.text if t.kind != "comment" else "\n" for t in tokens[i:end + 1])
                i = end + 1
                continue
            if followed_by_paren:
                if lower in _REFUSED_FUNCTIONS:
                    raise PromQLScopeError(f"'{word}()' is refused: it reads series the query does not name")
                out.append(word)
                i += 1
                continue
            if lower in _KEYWORDS or lower in _NUMBER_WORDS or lower in _AGGREGATIONS:
                out.append(word)
                i += 1
                continue
            # A metric name: the start of a vector selector.
            if nxt_tok is not None and nxt_tok.kind == "punct" and nxt_tok.text == "{":
                end = _matching(tokens, nxt, "{", "}")
                out.append(word + "{" + _scoped_matchers(tokens[nxt + 1:end], matcher) + "}")
                i = end + 1
            else:
                out.append(word + "{" + matcher + "}")
                i += 1
            selectors += 1
            continue
        out.append(tok.text)
        i += 1
    if any(t.kind == "punct" and t.text in "()" for t in tokens):
        _check_parens(tokens)
    logger.debug("scoped %d selector(s) to %s", selectors, allowed)
    return "".join(out)


def _check_parens(tokens: Sequence[_Token]) -> None:
    depth = 0
    for tok in tokens:
        if tok.kind == "punct" and tok.text == "(":
            depth += 1
        elif tok.kind == "punct" and tok.text == ")":
            depth -= 1
            if depth < 0:
                raise PromQLScopeError("unbalanced ')'")
    if depth:
        raise PromQLScopeError("unbalanced '('")


# --- Entitlement --------------------------------------------------------------


def namespaces_by_group() -> Dict[str, List[str]]:
    """METRICS_NAMESPACES_BY_GROUP: a JSON object {group: [namespace | "*"]}.

    Read per call (the chart sets it once; tests change it). Empty or unset means the
    matcher is off, which is the behaviour before WP-225. A malformed value fails
    closed: an empty mapping that is still "configured" refuses every caller."""
    raw = os.getenv("METRICS_NAMESPACES_BY_GROUP", "").strip()
    if not raw:
        return {}
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("METRICS_NAMESPACES_BY_GROUP is not valid JSON; every metrics query is refused")
        return {"": []}
    if not isinstance(doc, dict):
        logger.error("METRICS_NAMESPACES_BY_GROUP is not a JSON object; every metrics query is refused")
        return {"": []}
    if not doc:
        return {}  # "{}" (the chart default rendered as JSON) is no allowlist
    return {
        str(group): [str(ns) for ns in (value or []) if isinstance(ns, str)]
        for group, value in doc.items()
        if isinstance(value, list)
    } or {"": []}


@dataclass(frozen=True)
class Entitlement:
    configured: bool
    unrestricted: bool
    namespaces: tuple


def entitlement(groups: Sequence[str], mapping: Optional[Mapping[str, Sequence[str]]] = None) -> Entitlement:
    mapping = namespaces_by_group() if mapping is None else mapping
    if not mapping:
        return Entitlement(configured=False, unrestricted=True, namespaces=())
    allowed: set = set()
    for group in groups or []:
        for ns in mapping.get(group, ()):
            if ns == WILDCARD:
                return Entitlement(configured=True, unrestricted=True, namespaces=())
            allowed.add(ns)
    return Entitlement(configured=True, unrestricted=False, namespaces=tuple(sorted(allowed)))


QUERY_ARGUMENT = "query"
SCOPED_CAPABILITIES = ("metrics.query",)


def scope_arguments(capability: str, arguments: Dict[str, object], groups: Sequence[str]) -> Dict[str, object]:
    """The arguments to send for `capability`: unchanged unless the capability is a
    metrics query and the matcher is configured. Raises PermissionError when the
    caller has no namespace, PromQLScopeError when the query cannot be scoped."""
    if capability not in SCOPED_CAPABILITIES:
        return arguments
    ent = entitlement(groups)
    if not ent.configured or ent.unrestricted:
        return arguments
    if not ent.namespaces:
        raise PermissionError("no metrics namespace is entitled to the caller's groups (ADR-0603 M13)")
    query = arguments.get(QUERY_ARGUMENT)
    if not isinstance(query, str):
        raise PromQLScopeError(f"'{QUERY_ARGUMENT}' must be a PromQL string")
    return {**arguments, QUERY_ARGUMENT: scope_query(query, ent.namespaces)}
