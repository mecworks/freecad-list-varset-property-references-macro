# SPDX-License-Identifier: LGPL-2.1-or-later
# Copyright (c) 2026 Marc Christensen <mecworks@gmail.com>
#
# =====================================================================
# DEVELOPMENT COPY -- source of truth for the headless logic.
# Not shipped standalone: the distribution build
# (ListVarSetPropertyReferences.FCMacro, project root) embeds this module
# verbatim. Install only the generated single-file macro.
# =====================================================================
"""Headless logic for finding where VarSet properties are used in expressions.

This module is deliberately free of Qt and GUI code so it can be unit-tested
with plain Python fakes (see ``tests/test_core_unit.py``) and exercised inside
FreeCAD without a display (see ``tests/test_integration_freecad.py``).

Every function takes document/object references as arguments; nothing here
opens dialogs or touches the FreeCAD GUI.

API facts verified against FreeCAD 1.1.4 (evidence in ``research/PROBE_RESULTS.txt``):

* ``obj.ExpressionEngine`` is a **list of ``(property_name, expression)``
  tuples** -- not a dict (``.items()`` raises AttributeError).
* A freshly created ``App::VarSet`` reports exactly
  ``['ExpressionEngine', 'Label', 'Label2', 'Visibility']`` via
  ``PropertiesList``, which is what :data:`STANDARD_PROPERTIES` excludes.
* ``Document.getObjectsByType`` does **not exist** in 1.1.4; VarSets are
  located by type via ``isDerivedFrom`` (or ``doc.findObjects(Type=...)``).
* Expressions may reference objects in **other open documents** using the
  ``DocName#Object.Property`` syntax (wiki: *Expressions*, "Cross-document
  linking"); the referenced document must be loaded for the value to
  resolve. Such references store the full ``DocName#...`` text in the
  referring document's ``ExpressionEngine``, which is why scanning several
  documents matters (:func:`find_usages_all`).
* ``setExpression`` ACCEPTS a document name that exists nowhere: parsing
  does not require the referenced document to exist (forced identifiers are
  skipped by ``ObjectIdentifier::resolveAmbiguity``); the bound property
  simply sits Touched/Invalid until a document with that EXACT name opens,
  at which point the reference revives automatically. Name matching is
  case-sensitive. Bindings therefore become dead either by typo in the
  expression editor or AFTER creation -- e.g. when the referenced file is
  renamed. Dead bindings keep their last computed value silently;
  :func:`unresolved_doc_names` detects them by comparing each ``DocName#``
  token against the currently open document names, and the report
  formatters flag such lines with :data:`DEAD_REF_MARKER`.
"""

from __future__ import annotations

import re
from typing import Dict, Iterator, List, Optional, Tuple

#: TypeId of the native VarSet object (``src/App/VarSet.h``, added in
#: FreeCAD 1.0, PR #12135). Detection by type is authoritative; internal
#: names are user-editable and must not be relied upon.
VARSET_TYPE_ID = "App::VarSet"

#: Properties every DocumentObject carries that are not user variables.
#: Verified on FreeCAD 1.1.4: a bare App::VarSet's ``PropertiesList`` equals
#: this set exactly, so everything else on a VarSet is a user variable.
#:
#: This is a *pinned* baseline. If a future FreeCAD release adds standard
#: properties to DocumentObject/VarSet, they would leak into the variable
#: list unless the caller passes a dynamically probed baseline (a bare
#: VarSet's live ``PropertiesList``) via the *standard* argument of
#: :func:`user_properties` -- the macro does exactly that. The integration
#: test asserts this set still matches a live bare VarSet and fails loudly
#: on drift.
#:
#: Inverse edge case: a user property deliberately named after one of these
#: standard names (e.g. ``Label2``) is indistinguishable from the standard
#: property and is therefore excluded. Accepted trade-off.
STANDARD_PROPERTIES = frozenset(
    ("ExpressionEngine", "Label", "Label2", "Visibility")
)

#: Compiled-pattern cache keyed by (Name, Label, prop). The pattern is a
#: pure function of exactly those three strings, so a cached entry is always
#: correct; caching keeps repeated scans off the compile path.
_PATTERN_CACHE: Dict[Tuple[str, str, str], "re.Pattern"] = {}

#: Marker prefixing report lines whose expression references a document
#: that is not open (a dead cross-document binding).
DEAD_REF_MARKER = "(!)"

#: Characters that end a document-name token when scanning an expression
#: backwards from a ``#`` separator: whitespace plus every character that
#: is either illegal in a Windows file basename (document names derive
#: from file basenames) or acts as an operator/delimiter in expressions.
#: ``-`` is deliberately ADMITTED: it is legal in file basenames
#: (``My-File.FCStd``); the arithmetic-operator reading is recovered
#: separately in :func:`unresolved_doc_names`.
_DOCNAME_STOP = frozenset(
    " \t\r\n\x0b\x0c"           # whitespace
    "+/\\^%&|!?:=(),[]{};\"'`#"  # operators / delimiters
    "*?<>"                      # illegal in Windows file basenames
)


def is_varset(obj) -> bool:
    """Return True if *obj* is a VarSet (or a subclass), judged by type."""
    checker = getattr(obj, "isDerivedFrom", None)
    if callable(checker):
        return bool(checker(VARSET_TYPE_ID))
    return getattr(obj, "TypeId", None) == VARSET_TYPE_ID


def find_varsets(doc) -> List[object]:
    """All VarSet objects in *doc*, in document order."""
    return [obj for obj in doc.Objects if is_varset(obj)]


def iter_expressions(doc) -> Iterator[Tuple[object, str, str]]:
    """Yield ``(owner_object, bound_property, expression_text)`` for every
    expression bound anywhere in *doc*.

    Objects without an ``ExpressionEngine`` attribute or with an empty one
    are skipped silently. Engine entries that are not two-item sequences are
    skipped rather than raising, so a format drift in a future FreeCAD
    release degrades gracefully instead of crashing the scan.
    """
    for obj in doc.Objects:
        engine = getattr(obj, "ExpressionEngine", None)
        if not engine:
            continue
        for entry in engine:
            try:
                prop, expr = entry
            except (TypeError, ValueError):
                continue
            yield obj, prop, expr


def user_properties(varset, standard=STANDARD_PROPERTIES) -> List[str]:
    """User-defined variable names of *varset*, excluding *standard*.

    Order follows ``PropertiesList`` (alphabetical in FreeCAD 1.x).

    *standard* defaults to the pinned :data:`STANDARD_PROPERTIES`; pass a
    dynamically probed baseline (a bare VarSet's live ``PropertiesList``) to
    stay immune to upstream additions of standard properties.
    """
    return [p for p in varset.PropertiesList if p not in standard]


def _anchor_alternatives(varset) -> List[str]:
    """Escaped reference forms of *varset*: its internal Name and its
    ``<<Label>>`` form (both are kept, since expressions may use either)."""
    forms = {re.escape(varset.Name)}
    label = getattr(varset, "Label", None)
    if label:
        forms.add(re.escape("<<" + label + ">>"))
    return sorted(forms)


def usage_pattern(varset, prop: str) -> "re.Pattern":
    """Compile a regex matching references to *varset.prop* in an expression.

    Handles both reference styles documented on the Expressions wiki page:
    ``Name.Prop`` (internal name) and ``<<Label>>.Prop`` (label wrapped in
    angle brackets). Whitespace around the dot is tolerated.

    Both sides of the reference are guarded:

    * the trailing ``\\b`` rejects longer identifiers such as ``WidthX``;
    * the leading ``(?<!\\w)`` rejects references to *other* objects whose
      internal name merely ends with the selected VarSet's name
      (``MyDims.Width`` must not match when ``Dims`` is selected). Internal
      names are identifiers, so a preceding word character always means a
      longer identifier; ``<<Label>>`` references in valid expressions begin
      after whitespace, an operator, or start-of-string.

    Anchoring to the selected VarSet avoids false positives from other
    objects that happen to have a property with the same name.

    Cross-document references (``OtherDoc#Name.Prop`` or
    ``OtherDoc#<<Label>>.Prop``) match as well: the ``#`` separator is a
    non-word character, so the left-boundary guard passes, and the anchored
    reference text is identical to the local form.

    Compiled patterns are cached by (Name, Label, prop); since the pattern
    depends only on those strings, the cache can never serve a stale entry.
    """
    key = (getattr(varset, "Name", ""), getattr(varset, "Label", ""), prop)
    cached = _PATTERN_CACHE.get(key)
    if cached is None:
        anchors = "|".join(_anchor_alternatives(varset))
        cached = re.compile(rf"(?<!\w)(?:{anchors})\s*\.\s*{re.escape(prop)}\b")
        _PATTERN_CACHE[key] = cached
    return cached


def display_path(obj, prop: str) -> str:
    """Human-readable ``Owner.Property`` path for result lines.

    Shows the Label, appending the internal Name in parentheses when the two
    differ, so results stay unambiguous for duplicate labels.
    """
    label = getattr(obj, "Label", None) or obj.Name
    if label != obj.Name:
        return "{} ({}).{}".format(label, obj.Name, prop)
    return "{}.{}".format(label, prop)


def find_usages(doc, varset, prop: str,
                expressions: Optional[List[Tuple[object, str, str]]] = None
                ) -> List[Tuple[str, str]]:
    """All ``(display_path, expression)`` pairs referencing *varset.prop*.

    By default the scan walks the whole document on every call. Callers that
    scan repeatedly over an unchanged document -- e.g. the modal dialog,
    where expressions cannot change while ``exec()`` blocks the main window
    -- may pass a precomputed *expressions* snapshot taken once via
    :func:`iter_expressions`, sparing each selection change a rescan.
    """
    pattern = usage_pattern(varset, prop)
    source = iter_expressions(doc) if expressions is None else expressions
    return [
        (display_path(owner, bound_prop), expr)
        for owner, bound_prop, expr in source
        if pattern.search(expr)
    ]


def _doc_name_token(expr: str, hash_index: int, stop) -> str:
    """Token of characters immediately preceding ``expr[hash_index]``.

    Walks backwards until a character in *stop*; returns the empty string
    when the ``#`` sits at the start of the expression.
    """
    end = hash_index
    while end > 0 and expr[end - 1] not in stop:
        end -= 1
    return expr[end:hash_index]


def referenced_doc_names(expr: str) -> List[str]:
    """Document names referenced in *expr*, in first-seen order.

    Every ``<token>#`` occurrence contributes the longest plausible
    document-name token preceding the ``#`` (hyphens included, since they
    are legal in file basenames). Expressions without a ``#`` yield an
    empty list. Exposed for diagnostics and tests;
    :func:`unresolved_doc_names` is the workhorse.
    """
    names: List[str] = []
    seen = set()
    for match in re.finditer("#", expr):
        token = _doc_name_token(expr, match.start(), _DOCNAME_STOP)
        if token and token not in seen:
            seen.add(token)
            names.append(token)
    return names


def unresolved_doc_names(expr: str, open_doc_names) -> List[str]:
    """Names referenced in *expr* that are not in *open_doc_names*.

    A reference counts as resolved when its document-name token -- or, for
    a hyphen-bearing token, the trailing piece after the last hyphen --
    matches an open document name exactly. Matching is case-sensitive,
    mirroring the expression parser, which rejects ``ghostdoc2#...`` even
    while ``GHOSTDOC2`` is open (evidence:
    ``research/PROBE_DEADREF.txt``).

    Why the extra hyphen reading: a hyphen may belong to the file basename
    (``My-File#Obj.Prop``) or be a minus operator written tight against
    the reference (``2-OtherDoc#Dims.Width``, ``-X#Y.Z``). The operator
    reading is offered only when the segment before the last hyphen is
    empty or purely numeric -- the shapes a numeric literal or unary minus
    takes -- so a hyphenated basename like ``Renamed-Away`` is never
    mistaken for ``Something - Away``. A genuinely dead reference (its
    master file renamed away) fails every reading and is reported under
    its full hyphen-inclusive name.

    Returns unique offenders in first-seen order; an empty list means
    every referenced document is open.
    """
    open_set = set(open_doc_names)
    offenders: List[str] = []
    seen = set()
    for match in re.finditer("#", expr):
        token = _doc_name_token(expr, match.start(), _DOCNAME_STOP)
        if not token or token in seen:
            continue
        alt = None
        dash = token.rfind("-")
        if dash != -1 and (token[:dash] == "" or token[:dash].isdigit()):
            alt = token[dash + 1:]
        if token not in open_set and (alt is None or alt not in open_set):
            seen.add(token)
            offenders.append(token)
    return offenders


def _dead_ref_legend(offenders: List[str]) -> str:
    """Footer explaining :data:`DEAD_REF_MARKER` lines."""
    lines = [
        "{} references a document that is not open; its value is frozen "
        "at the last computed result.".format(DEAD_REF_MARKER),
    ]
    if offenders:
        lines.append(
            "Missing documents: {}".format(
                ", ".join(sorted(set(offenders))))
        )
    return "\n".join(lines)


def find_usages_all(docs, varset, prop: str,
                    snapshots: Optional[Dict[int, List[Tuple[object, str, str]]]] = None
                    ) -> List[Tuple[object, str, str]]:
    """Scan several documents for references to *varset.prop*.

    Returns ``(source_document, display_path, expression)`` triples in
    document order. *snapshots* optionally maps ``id(doc)`` to a
    precomputed expression list (same contract as :func:`find_usages`);
    documents without a snapshot are scanned live.

    Needed because expressions may legally reference a VarSet from another
    open document (``OtherDoc#VarSet.Prop``); such usages live in the
    *referring* document and are invisible to a single-document scan.
    """
    results: List[Tuple[object, str, str]] = []
    for doc in docs:
        snap = snapshots.get(id(doc)) if snapshots is not None else None
        for path, expr in find_usages(doc, varset, prop, expressions=snap):
            results.append((doc, path, expr))
    return results


def format_report(matches: List[Tuple[str, str]],
                  open_doc_names=None) -> str:
    """Format result lines; returns a friendly placeholder when empty.

    When *open_doc_names* (the names of all currently open documents) is
    given, lines whose expression references a document that is not open
    are prefixed with :data:`DEAD_REF_MARKER` and a legend is appended --
    such bindings are dead: FreeCAD keeps their last computed value
    silently instead of erroring, typically after the referenced file was
    renamed. Omitting it reproduces the plain output byte-for-byte.
    """
    if not matches:
        return "(no usages found)"
    lines = []
    offenders: List[str] = []
    flagged = 0
    for path, expr in matches:
        missing = (
            unresolved_doc_names(expr, open_doc_names)
            if open_doc_names is not None else [])
        if missing:
            flagged += 1
            offenders.extend(missing)
            lines.append("{} {} = {}".format(DEAD_REF_MARKER, path, expr))
        else:
            lines.append("{} = {}".format(path, expr))
    if flagged:
        lines.append("")
        lines.append(_dead_ref_legend(offenders))
    return "\n".join(lines)


def format_report_multi(matches: List[Tuple[object, str, str]], home_doc,
                        open_doc_names=None) -> str:
    """Format multi-document result lines from :func:`find_usages_all`.

    *matches* are ``(doc, display_path, expression)`` triples. Lines whose
    usage lives outside *home_doc* are prefixed with ``[<document label>]``
    so cross-file usages are unambiguous; local lines keep their plain
    form, keeping single-document output identical to :func:`format_report`.

    *open_doc_names* enables dead-reference flagging exactly as in
    :func:`format_report` (see there).
    """
    if not matches:
        return "(no usages found)"
    lines = []
    offenders: List[str] = []
    flagged = 0
    for doc, path, expr in matches:
        missing = (
            unresolved_doc_names(expr, open_doc_names)
            if open_doc_names is not None else [])
        if doc is home_doc:
            base = "{} = {}".format(path, expr)
        else:
            label = getattr(doc, "Label", None) or getattr(doc, "Name", "?")
            base = "[{}] {} = {}".format(label, path, expr)
        if missing:
            flagged += 1
            offenders.extend(missing)
            lines.append("{} {}".format(DEAD_REF_MARKER, base))
        else:
            lines.append(base)
    if flagged:
        lines.append("")
        lines.append(_dead_ref_legend(offenders))
    return "\n".join(lines)
