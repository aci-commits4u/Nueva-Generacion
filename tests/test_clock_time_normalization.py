from app.temporal import clock_time_in_quote, extract_clock_times


def test_clock_normalization_accepts_dotted_meridiems():
    quote = "show departures between 8 a.m. and 8 p.m."
    assert extract_clock_times(quote) == ["08:00", "20:00"]
    assert clock_time_in_quote("08:00", quote)
    assert clock_time_in_quote("20:00", quote)


def test_clock_normalization_accepts_machine_and_human_forms():
    assert extract_clock_times("between 08:00 and 20:00") == ["08:00", "20:00"]
    assert extract_clock_times("between 8:30 a.m. and 12:00 p.m.") == [
        "08:30",
        "12:00",
    ]
    assert extract_clock_times("8:00 p.m. and 12:30 a.m.") == ["20:00", "00:30"]
    assert extract_clock_times("12:30 p.m.") == ["12:30"]


def test_clock_normalization_does_not_mix_24_hour_values_with_meridiems():
    quote = "8:00 p.m. and 9:00 p.m."
    assert clock_time_in_quote("20:00", quote)
    assert clock_time_in_quote("21:00", quote)
    assert not clock_time_in_quote("08:00", quote)
    assert not clock_time_in_quote("09:00", quote)


def test_clock_normalization_does_not_turn_dates_or_bare_numbers_into_times():
    quote = "any date from May 5 through May 9, 2027 under $1,200"
    assert extract_clock_times(quote) == []
    assert not clock_time_in_quote("08:00", quote)
    assert not clock_time_in_quote("8 am", "depart after 8")


def test_clock_normalization_rejects_invalid_requirement_values():
    assert not clock_time_in_quote("25:00", "25:00")
    assert extract_clock_times("13:00 p.m. 8:60 p.m.") == []
    assert not clock_time_in_quote("08:00", None)

