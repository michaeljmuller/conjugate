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
