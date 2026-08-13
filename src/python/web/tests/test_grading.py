from web.grading import grade


def test_exact_match_is_correct():
    v = grade("venho", "venho")
    assert v.is_correct and v.verdict == "correct"


def test_case_and_whitespace_insensitive():
    assert grade("  VeNho  ", "venho").is_correct


def test_missing_accent_is_wrong():
    # No automatic accent tolerance — the user can reclassify as a typo instead.
    v = grade("venho", "vênho")
    assert not v.is_correct and v.verdict == "wrong"


def test_different_form_is_wrong():
    v = grade("venha", "venho")
    assert v.verdict == "wrong" and not v.is_correct


def test_empty_is_wrong():
    assert grade("", "venho").verdict == "wrong"


# ---- alternative forms ---------------------------------------------------

def test_any_accepted_form_is_correct():
    """Portuguese offers genuine alternatives in some cells, so the drill takes
    them all rather than insisting on the one it happened to display."""
    v = grade("ouço", "oiço", ["ouço"])
    assert v.is_correct and v.verdict == "correct"
    # The displayed form is reported back regardless of which was typed, so the
    # UI can offer the others.
    assert v.correct_answer == "oiço"
    assert v.matched == "ouço"


def test_the_displayed_form_still_grades():
    v = grade("oiço", "oiço", ["ouço"])
    assert v.is_correct and v.matched == "oiço"


def test_a_form_outside_the_accepted_set_is_wrong():
    assert not grade("ouvo", "oiço", ["ouço"]).is_correct


def test_no_variants_behaves_as_before():
    assert grade("corro", "corro").is_correct
    assert not grade("corres", "corro").is_correct


def test_variants_are_matched_case_and_whitespace_insensitively():
    assert grade("  OUÇO ", "oiço", ["ouço"]).is_correct


def test_variants_are_still_accent_sensitive():
    """Accents are the thing being drilled; a variant does not relax that."""
    assert not grade("ouco", "oiço", ["ouço"]).is_correct
