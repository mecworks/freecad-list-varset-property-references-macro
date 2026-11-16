"""Unit tests for varset_usage_core_dev using lightweight fakes.

No FreeCAD or Qt is required, so these run under any CPython 3 interpreter:

    python tests/test_core_unit.py

They are also pytest-compatible:

    pytest tests/test_core_unit.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "src"))

import varset_usage_core_dev as core  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeObj:
    """Mimics the small surface of App.DocumentObject used by the core."""

    def __init__(self, name, label=None, type_id="App::FeaturePython",
                 properties=("ExpressionEngine", "Label", "Label2", "Visibility"),
                 expressions=None):
        self.Name = name
        self.Label = label if label is not None else name
        self.TypeId = type_id
        self.PropertiesList = list(properties)
        self.ExpressionEngine = list(expressions or [])

    def isDerivedFrom(self, type_id):
        return self.TypeId == type_id


class FakeDoc:
    def __init__(self, objects, name="Doc"):
        self.Objects = list(objects)
        self.Name = name
        self.Label = name


def make_varset(name, label=None, extra_props=()):
    props = ("ExpressionEngine", "Label", "Label2", "Visibility") + tuple(extra_props)
    return FakeObj(name, label=label, type_id="App::VarSet", properties=props)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_find_varsets_filters_by_type_not_name():
    doc = FakeDoc([
        make_varset("MyVars"),
        FakeObj("VarSetLikeName", type_id="App::FeaturePython"),  # name trap
        FakeObj("RenamedInternally", label="Dims", type_id="App::VarSet"),
    ])
    found = core.find_varsets(doc)
    assert [o.Name for o in found] == ["MyVars", "RenamedInternally"]


def test_user_properties_excludes_standard_and_keeps_order():
    vs = make_varset("V", extra_props=("Width", "Height", "Tolerance"))
    assert core.user_properties(vs) == ["Width", "Height", "Tolerance"]


def test_user_properties_respects_custom_standard_set():
    # A dynamically probed baseline may exclude more than the pinned set.
    vs = make_varset("V", extra_props=("Width", "Status"))
    extended = frozenset(("ExpressionEngine", "Label", "Label2",
                          "Visibility", "Status"))
    assert core.user_properties(vs, standard=extended) == ["Width"]
    assert core.user_properties(vs) == ["Width", "Status"]


def test_bare_varset_has_no_user_properties():
    vs = make_varset("V")
    assert core.user_properties(vs) == []


def test_iter_expressions_skips_missing_engine_and_empty():
    with_engine = FakeObj("A", expressions=[("Len", "1mm")])
    without_attr = FakeObj.__new__(FakeObj)
    without_attr.Name = "B"
    without_attr.Label = "B"
    empty = FakeObj("C", expressions=[])
    doc = FakeDoc([with_engine, without_attr, empty])
    got = list(core.iter_expressions(doc))
    assert [(o.Name, p, e) for o, p, e in got] == [("A", "Len", "1mm")]
    assert got[0][0] is with_engine


def test_iter_expressions_skips_malformed_entries():
    bad = FakeObj.__new__(FakeObj)
    bad.Name = "Bad"
    bad.Label = "Bad"
    bad.ExpressionEngine = [("OnlyOne",), ("A", "expr"), 42]
    got = list(core.iter_expressions(FakeDoc([bad])))
    assert [(o.Name, p, e) for o, p, e in got] == [("Bad", "A", "expr")]


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _vs(name="Dims", label=None):
    return make_varset(name, label=label, extra_props=("Width",))


def test_pattern_matches_internal_name_reference():
    pat = core.usage_pattern(_vs(), "Width")
    assert pat.search("Dims.Width * 2")


def test_pattern_matches_double_bracket_label_reference():
    pat = core.usage_pattern(_vs(label="My Dims"), "Width")
    assert pat.search("<<My Dims>>.Width + 1mm")


def test_pattern_tolerates_whitespace_around_dot():
    pat = core.usage_pattern(_vs(), "Width")
    assert pat.search("Dims . Width")
    assert pat.search("Dims. Width")


def test_pattern_rejects_longer_identifiers():
    pat = core.usage_pattern(_vs(), "Width")
    assert not pat.search("Dims.WidthX")
    assert not pat.search("Dims.MyWidth")


def test_pattern_rejects_other_objects_with_same_property():
    pat = core.usage_pattern(_vs(), "Width")
    assert not pat.search("Other.Width")
    assert not pat.search("<<Other>>.Width")


def test_pattern_rejects_superset_names():
    # Regression: an object whose internal name merely ENDS WITH the
    # selected VarSet's name must not match (left word-boundary guard).
    pat = core.usage_pattern(_vs(), "Width")   # _vs() Name="Dims"
    assert not pat.search("MyDims.Width * 2")
    assert not pat.search("xDims . Width")
    assert not pat.search("SuperDims.Width * 3")
    # ...while genuine references still match:
    assert pat.search("Dims.Width * 2")
    assert pat.search("= Dims.Width")
    assert pat.search("[Dims.Width]")


def test_pattern_escapes_special_characters_in_label():
    pat = core.usage_pattern(_vs(label="My Set (v2)"), "Width")
    assert pat.search("<<My Set (v2)>>.Width")
    # The unescaped parens must not act as a group:
    assert not pat.search("<<My Set X v2 >>.Width")


def test_both_reference_styles_match_when_name_equals_label():
    vs = _vs(label="Dims")
    pat = core.usage_pattern(vs, "Width")
    assert pat.search("Dims.Width")
    assert pat.search("<<Dims>>.Width")


def test_pattern_matches_cross_document_reference():
    # DocName#Object.Property (wiki: Expressions, Cross-document linking).
    # The '#' separator is a non-word char, so the left-boundary guard
    # passes and the anchored reference text still matches.
    pat = core.usage_pattern(_vs(), "Width")   # Name="Dims"
    assert pat.search("Master_File#Dims.Width * 2")
    labeled = core.usage_pattern(_vs(label="My Dims"), "Width")
    assert labeled.search("VentFile#<<My Dims>>.Width + 1mm")
    # A different object in another document must still not match:
    assert not pat.search("OtherDoc#MyDims.Width * 2")


# ---------------------------------------------------------------------------
# End-to-end on fakes
# ---------------------------------------------------------------------------

def test_display_path_prefers_label_and_disambiguates():
    same = FakeObj("Pad001")
    diff = FakeObj("Pad002", label="Big Pad")
    assert core.display_path(same, "Length") == "Pad001.Length"
    assert core.display_path(diff, "Length") == "Big Pad (Pad002).Length"


def test_find_usages_end_to_end():
    dims = _vs()
    decoy = make_varset("Decoy", extra_props=("Width",))
    t1 = FakeObj("UsesName", expressions=[("Len", "Dims.Width * 2")])
    t2 = FakeObj("UsesLabel", expressions=[("Len", "<<Dims>>.Width + 1mm")])
    t3 = FakeObj("UsesDecoy", expressions=[("Len", "Decoy.Width")])
    t4 = FakeObj("Unrelated", expressions=[("Len", "1mm + 2mm")])
    # Decoy whose name ends with the selected VarSet's name and which
    # references its own same-named property (superset-name trap).
    t5 = FakeObj("SuperDims", expressions=[("Len", "SuperDims.Width * 3")])
    doc = FakeDoc([dims, decoy, t1, t2, t3, t4, t5])

    hits = core.find_usages(doc, dims, "Width")
    assert sorted(p for p, _ in hits) == ["UsesLabel.Len", "UsesName.Len"]
    exprs = dict(hits)
    assert exprs["UsesName.Len"] == "Dims.Width * 2"


def test_find_usages_accepts_expression_snapshot():
    dims = _vs()
    t1 = FakeObj("UsesName", expressions=[("Len", "Dims.Width * 2")])
    doc = FakeDoc([dims, t1])
    snapshot = list(core.iter_expressions(doc))
    hits = core.find_usages(doc, dims, "Width", expressions=snapshot)
    assert [(p, e) for p, e in hits] == [("UsesName.Len", "Dims.Width * 2")]


def test_find_usages_all_scans_multiple_documents():
    dims = _vs()
    local = FakeObj("UsesName", expressions=[("Len", "Dims.Width * 2")])
    xref = FakeObj("Part",
                   expressions=[("Len", "HomeDoc#Dims.Width * 3")])
    home = FakeDoc([dims, local], name="HomeDoc")
    away = FakeDoc([xref], name="VentFile")
    hits = core.find_usages_all([home, away], dims, "Width")
    assert [(d.Name, p) for d, p, _ in hits] == [
        ("HomeDoc", "UsesName.Len"), ("VentFile", "Part.Len")]
    assert hits[0][0] is home and hits[1][0] is away


def test_find_usages_all_uses_snapshots():
    dims = _vs()
    local = FakeObj("UsesName", expressions=[("Len", "Dims.Width * 2")])
    home = FakeDoc([dims, local], name="Home")
    away = FakeDoc([], name="Away")
    snaps = {id(home): list(core.iter_expressions(home)), id(away): []}
    hits = core.find_usages_all([home, away], dims, "Width", snapshots=snaps)
    assert [(d.Name, p) for d, p, _ in hits] == [("Home", "UsesName.Len")]


def test_format_report_multi_prefixes_foreign_docs_only():
    home = FakeDoc([], name="Home")
    away = FakeDoc([], name="Away")
    text = core.format_report_multi(
        [(home, "A.Len", "1mm"), (away, "B.Len", "2mm")], home)
    assert text == "A.Len = 1mm\n[Away] B.Len = 2mm"
    assert core.format_report_multi([], home) == "(no usages found)"


def test_format_report_empty_placeholder():
    assert core.format_report([]) == "(no usages found)"


def test_format_report_lines():
    lines = core.format_report([("A.B", "1"), ("C.D", "2")])
    assert lines == "A.B = 1\nC.D = 2"


# ---------------------------------------------------------------------------
# Dead cross-document reference detection
# ---------------------------------------------------------------------------

def test_referenced_doc_names_basic():
    assert core.referenced_doc_names("GhostDoc#Vars.W * 2") == ["GhostDoc"]


def test_referenced_doc_names_multiple_and_deduped():
    expr = "A#X.P + B#Y.Q + A#Z.R"
    assert core.referenced_doc_names(expr) == ["A", "B"]


def test_referenced_doc_names_local_expression_yields_none():
    assert core.referenced_doc_names("Dims.Width * 2") == []
    assert core.referenced_doc_names("<<My Dims>>.Width + 1mm") == []


def test_referenced_doc_names_tight_operators_and_parens():
    # Operators and delimiters terminate the token; only the name remains.
    assert core.referenced_doc_names("2*X#Y.Z") == ["X"]
    assert core.referenced_doc_names("(X#Y.Z)") == ["X"]
    assert core.referenced_doc_names("a=X#Y.Z") == ["X"]


def test_referenced_doc_names_hyphenated_basename_kept_whole():
    # Hyphens are legal in file basenames, so the loose reading keeps them.
    assert core.referenced_doc_names("My-File#Obj.P") == ["My-File"]


def test_unresolved_flags_missing_document():
    open_docs = {"Home", "VentFile"}
    assert core.unresolved_doc_names(
        "OldName#Vars.W * 2", open_docs) == ["OldName"]


def test_unresolved_accepts_open_document():
    open_docs = {"Master_File"}
    assert core.unresolved_doc_names(
        "Master_File#VarSet.RackEarWidth * 2", open_docs) == []
    # Local expressions never reference a document.
    assert core.unresolved_doc_names("Dims.Width * 2", open_docs) == []


def test_unresolved_is_case_sensitive_like_the_parser():
    # Verified on FreeCAD 1.1.4: with 'GHOSTDOC2' open, setExpression()
    # rejects 'ghostdoc2#...' (research/PROBE_DEADREF.txt), so matching
    # must be exact-case to mirror resolution behaviour.
    assert core.unresolved_doc_names("ghostdoc2#V.W", {"GHOSTDOC2"}) == [
        "ghostdoc2"]


def test_unresolved_hyphen_in_basename_does_not_false_alarm():
    # Doc named 'My-File' is open: the hyphen-inclusive reading resolves.
    assert core.unresolved_doc_names("My-File#O.P", {"My-File"}) == []


def test_unresolved_tight_minus_before_reference_does_not_false_alarm():
    # '2-X#Y.Z' with doc 'X' open: the segment before the last hyphen is
    # purely numeric, so the operator reading ('X') resolves the ref.
    assert core.unresolved_doc_names("2-X#Y.Z", {"X"}) == []


def test_unresolved_unary_minus_before_reference_does_not_false_alarm():
    # '-X#Y.Z' (negation written tight) with doc 'X' open.
    assert core.unresolved_doc_names("-X#Y.Z", {"X"}) == []


def test_unresolved_hyphenated_dead_ref_not_rescued_by_open_suffix():
    # 'Renamed-Away#...' is dead even though a document named 'Away'
    # happens to be open: the segment before the last hyphen is not
    # numeric, so no operator reading is offered.
    assert core.unresolved_doc_names(
        "Renamed-Away#V.W * 3", {"Away"}) == ["Renamed-Away"]


def test_unresolved_reports_full_name_for_dead_hyphenated_ref():
    # Master renamed away: neither reading matches, offender reported
    # under its full hyphen-inclusive name.
    assert core.unresolved_doc_names("Old-Name#C.D", {"Other"}) == [
        "Old-Name"]


def test_unresolved_dedupes_repeated_offenders():
    assert core.unresolved_doc_names(
        "G#A.B + G#C.D", {}) == ["G"]


def test_unresolved_accepts_any_iterable_of_names():
    assert core.unresolved_doc_names("G#A.B", ["H", "G"]) == []


def test_format_report_flags_dead_refs_with_legend():
    matches = [
        ("Pad.Len", "OldName#Vars.W * 2"),
        ("Rim.Len", "LiveDoc#Vars.T"),
    ]
    text = core.format_report(matches, open_doc_names={"LiveDoc"})
    lines = text.split("\n")
    assert lines[0] == "(!) Pad.Len = OldName#Vars.W * 2"
    assert lines[1] == "Rim.Len = LiveDoc#Vars.T"   # live line untouched
    assert "Missing documents: OldName" in text
    assert core.DEAD_REF_MARKER in text


def test_format_report_no_flag_when_all_documents_open():
    matches = [("Pad.Len", "LiveDoc#Vars.W * 2")]
    text = core.format_report(matches, open_doc_names={"LiveDoc"})
    assert text == "Pad.Len = LiveDoc#Vars.W * 2"  # no marker, no legend


def test_format_report_backward_compatible_without_open_doc_names():
    matches = [("A.B", "1"), ("C.D", "2")]
    assert core.format_report(matches) == "A.B = 1\nC.D = 2"
    assert core.format_report([]) == "(no usages found)"
    assert core.format_report([], open_doc_names={"X"}) == "(no usages found)"


def test_format_report_multi_flags_dead_refs_across_docs():
    home = FakeDoc([], name="Home")
    away = FakeDoc([], name="Away")
    matches = [
        (home, "A.Len", "Home#V.W"),
        (away, "B.Len", "Renamed-Away#V.W * 3"),
    ]
    text = core.format_report_multi(matches, home,
                                    open_doc_names={"Home", "Away"})
    lines = text.split("\n")
    assert lines[0] == "A.Len = Home#V.W"
    assert lines[1] == "(!) [Away] B.Len = Renamed-Away#V.W * 3"
    assert "Missing documents: Renamed-Away" in text


def test_format_report_multi_legacy_call_unchanged():
    home = FakeDoc([], name="Home")
    away = FakeDoc([], name="Away")
    text = core.format_report_multi(
        [(home, "A.Len", "1mm"), (away, "B.Len", "2mm")], home)
    assert text == "A.Len = 1mm\n[Away] B.Len = 2mm"


# ---------------------------------------------------------------------------
# Runner (plain Python, no pytest dependency)
# ---------------------------------------------------------------------------

def _run_all():
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures += 1
            print("FAIL {} : {}".format(name, exc))
        else:
            print("PASS {}".format(name))
    total = len(tests)
    print("\n{}/{} passed".format(total - failures, total))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    _run_all()
