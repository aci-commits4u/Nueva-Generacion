from datetime import date

from app.temporal import expand_date_quote, reference_for_quote, resolve_date_choice


def test_explicit_yearful_date_and_iso_are_always_supported_without_anchor():
    assert resolve_date_choice("October 14th, 2026") == "2026-10-14"
    assert resolve_date_choice("2026-10-14") == "2026-10-14"


def test_shared_year_range_uses_reference_year():
    assert resolve_date_choice("Oct 14th through oct 21st", "2026-10-13") == {
        "start": "2026-10-14",
        "end": "2026-10-21",
    }
    assert resolve_date_choice("Nov 7–10", date(2026, 10, 13)) == {
        "start": "2026-11-07",
        "end": "2026-11-10",
    }


def test_cross_month_range_and_past_range_roll_forward():
    assert resolve_date_choice("Dec 30-Jan 2", "2026-12-20") == {
        "start": "2026-12-30",
        "end": "2027-01-02",
    }
    assert resolve_date_choice("Nov 7–10", "2026-11-15") == {
        "start": "2027-11-07",
        "end": "2027-11-10",
    }


def test_discrete_dates_are_alternatives_not_a_continuous_range():
    assert resolve_date_choice("Oct 14 or 21", "2026-10-13") == {
        "dates": ["2026-10-14", "2026-10-21"]
    }
    assert resolve_date_choice("Oct 14 or 21.", "2026-10-13") == {
        "dates": ["2026-10-14", "2026-10-21"]
    }
    assert resolve_date_choice("2026-10-14 or 2026-10-21") == {
        "dates": ["2026-10-14", "2026-10-21"]
    }
    assert resolve_date_choice("These dates work: 2026-10-14, 2026-10-21") == {
        "dates": ["2026-10-14", "2026-10-21"]
    }


def test_ui_between_iso_phrase_is_an_interval():
    assert resolve_date_choice(
        "Travel between 2026-10-14 and 2026-10-21, inclusive."
    ) == {"start": "2026-10-14", "end": "2026-10-21"}


def test_expand_date_quote_recovers_the_customer_range_without_inventing_text():
    source = "Book nonstop EWR to MCO under $200 from Oct 14th through Oct 21st."
    assert expand_date_quote("Oct 14th", source) == "Oct 14th through Oct 21st"
    assert expand_date_quote("Oct 14th through Oct 21st", source) == "Oct 14th through Oct 21st"


def test_expand_date_quote_handles_unique_alternatives_and_rejects_ambiguity():
    source = "I can travel Oct 14 or Oct 21."
    assert expand_date_quote("Oct 14", source) == "Oct 14 or Oct 21"
    assert expand_date_quote("Oct 21", source) == "Oct 14 or Oct 21"
    assert expand_date_quote(
        "Oct 14", "Oct 14 works, but Oct 14 through Oct 21 also works"
    ) == "Oct 14 through Oct 21"
    assert expand_date_quote(
        "Oct 14", "Oct 14 through Oct 21, or Oct 14 through Oct 22"
    ) is None


def test_relative_dates_use_trusted_anchor():
    assert resolve_date_choice("today", "2026-10-13") == "2026-10-13"
    assert resolve_date_choice("tomorrow", "2026-10-13") == "2026-10-14"
    assert resolve_date_choice("within the next week", "2026-10-13") == {
        "start": "2026-10-14",
        "end": "2026-10-20",
    }
    assert resolve_date_choice("next 7 days", "2026-10-13") == {
        "start": "2026-10-14",
        "end": "2026-10-20",
    }
    assert resolve_date_choice("next week", "2026-10-13") == {
        "start": "2026-10-19",
        "end": "2026-10-25",
    }
    assert resolve_date_choice("next Friday", "2026-10-13") == "2026-10-16"
    assert resolve_date_choice("this Friday", "2026-10-16") == "2026-10-16"
    assert resolve_date_choice("next Friday") is None


def test_numeric_dates_only_resolve_when_the_slash_order_is_unambiguous():
    assert resolve_date_choice("10/14/2026") == "2026-10-14"
    assert resolve_date_choice("14/10/2026") == "2026-10-14"
    assert resolve_date_choice("10/11/2026") is None


def test_yearless_and_relative_phrases_require_an_anchor():
    assert resolve_date_choice("October 14") is None
    assert resolve_date_choice("tomorrow") is None
    assert resolve_date_choice("Oct 14 through Oct 21") is None


def test_soft_negated_approximate_and_unrelated_phrases_stay_unresolved():
    for quote in ("not Oct 14", "preferably Oct 14", "maybe Oct 14", "early November", "the airport is open"):
        assert resolve_date_choice(quote, "2026-10-13") is None


def test_invalid_and_unbounded_values_stay_unresolved():
    assert resolve_date_choice("February 30, 2026") is None
    assert resolve_date_choice("Jan 1, 2026 through Jan 3, 2027") is None
    assert resolve_date_choice("Jan 1 or Feb 2 or Mar 3", "2026-01-01") == {
        "dates": ["2026-01-01", "2026-02-02", "2026-03-03"]
    }


def test_reference_for_quote_uses_latest_matching_customer_message_only():
    messages = [
        {"role": "assistant", "content": "Which date? Oct 14", "timestamp": "2026-10-20T23:00:00Z"},
        {"role": "user", "content": "Oct 14", "timestamp": "2026-10-13T10:00:00Z"},
        {"role": "customer", "content": "I changed that: Oct 14", "timestamp": "2026-10-14T01:00:00+00:00"},
    ]
    assert reference_for_quote("Oct 14", messages) == "2026-10-14"


def test_reference_for_quote_rejects_non_utc_or_missing_timestamps():
    messages = [
        {"role": "user", "content": "Oct 14", "timestamp": "2026-10-13T10:00:00"},
        {"role": "user", "content": "Oct 14", "timestamp": "2026-10-13T10:00:00-04:00"},
    ]
    assert reference_for_quote("Oct 14", messages) is None
    assert reference_for_quote("Oct 14", None) is None


def test_reference_for_quote_prefers_trusted_local_reference_date_over_utc_rollover():
    messages = [
        {
            "role": "user",
            "content": "within the next week",
            # 20:15 on Oct 13 in New York is already Oct 14 in UTC.
            "timestamp": "2026-10-14T00:15:00Z",
            "reference_date": "2026-10-13",
        }
    ]
    anchor = reference_for_quote("within the next week", messages)
    assert anchor == "2026-10-13"
    assert resolve_date_choice(anchor and "within the next week", anchor) == {
        "start": "2026-10-14",
        "end": "2026-10-20",
    }


def test_short_non_messages_and_reply_metadata_are_safe():
    assert reference_for_quote("Yes", [{"role": "assistant", "reply_to": None}]) is None
    assert reference_for_quote("Yes", [{"role": "user", "reply_to": {"question": "Yes"}}]) is None
    assert resolve_date_choice(None) is None

