"""Unit tests for pure KNPC & KOC schedule calculations and exporters."""

from datetime import date

from app.schedule import (
    EPOCH_DATE,
    SHIFT_CYCLES,
    build_schedule,
    export_csv,
    export_ics,
    get_cycle_position,
    get_day_detail,
    get_kuwait_holidays,
    get_shift_for_date,
    resolve_date_range,
)


def test_epoch_and_cycle_parity_all_groups():
    """Verify exact parity with legacy cycle definitions at, after, and before epoch."""
    # Day 0 = 2024-10-06 (epoch), Day 1 = 2024-10-07, etc.
    for (company, group), cycle in SHIFT_CYCLES.items():
        for offset in range(len(cycle) * 2):
            target = date.fromordinal(EPOCH_DATE.toordinal() + offset)
            assert get_shift_for_date(target, company, group) == cycle[offset % len(cycle)]

        # Dates BEFORE epoch (Python modulo handles negative offsets symmetrically)
        prev_day = date.fromordinal(EPOCH_DATE.toordinal() - 1)
        assert get_shift_for_date(prev_day, company, group) == cycle[-1]

    # Boundary dates: 2020-01-01, leap day 2028-02-29, 2050-12-31
    assert get_shift_for_date(date(2020, 1, 1), "KNPC", "A") in {"Morning", "Afternoon", "Night", "Off"}
    assert get_shift_for_date(date(2028, 2, 29), "KOC", "C") in {"Morning", "Afternoon", "Night", "Off"}
    assert get_shift_for_date(date(2050, 12, 31), "KNPC", "D") in {"Morning", "Afternoon", "Night", "Off"}


def test_cycle_position():
    """Verify 1-indexed cycle day reporting."""
    assert get_cycle_position(EPOCH_DATE, "KNPC", "A") == (1, 8)
    assert get_cycle_position(date(2024, 10, 13), "KNPC", "A") == (8, 8)
    assert get_cycle_position(EPOCH_DATE, "KOC", "B") == (1, 4)
    assert get_cycle_position(date(2024, 10, 9), "KOC", "B") == (4, 4)


def test_kuwait_holidays_lookup():
    """Verify official Kuwaiti public holidays load in English."""
    kw_2026 = get_kuwait_holidays(2026)
    assert kw_2026[date(2026, 2, 25)] == "National Day"
    assert kw_2026[date(2026, 2, 26)] == "Liberation Day"


def test_long_weekends_only_consecutive_fri_sat_off():
    """Long weekends require BOTH Friday and Saturday to be Off."""
    # Check across a 1-year window for KNPC A
    start_d = date(2026, 1, 1)
    end_d = date(2026, 12, 31)
    result = build_schedule("KNPC", "A", start_d, end_d, today=date(2026, 11, 22))

    assert len(result.long_weekends) > 0
    for lw in result.long_weekends:
        assert lw.friday.date.weekday() == 4  # Friday
        assert lw.saturday.date.weekday() == 5  # Saturday
        assert (lw.saturday.date - lw.friday.date).days == 1
        assert lw.friday.shift == "Off"
        assert lw.saturday.shift == "Off"
        assert lw.friday.is_long_weekend is True
        assert lw.saturday.is_long_weekend is True

    # Ensure no isolated single-day Off Friday without Saturday Off is flagged
    lw_dates = {lw.friday.date for lw in result.long_weekends} | {
        lw.saturday.date for lw in result.long_weekends
    }
    for entry in result.entries:
        if entry.is_long_weekend:
            assert entry.date in lw_dates


def test_sunday_first_month_grid_alignment():
    """Month grid columns must align Sunday=0 through Friday=5, Saturday=6."""
    # November 2026 starts on Sunday (Nov 1, 2026)
    result = build_schedule("KNPC", "A", date(2026, 11, 1), date(2026, 11, 30), today=date(2026, 11, 22))
    assert len(result.month_grids) == 1
    grid = result.month_grids[0]
    first_week = grid.weeks[0]
    assert first_week[0] is not None
    assert first_week[0].day_num == 1
    assert first_week[0].entry.day_name == "Sunday"
    assert first_week[5] is not None
    assert first_week[5].entry.day_name == "Friday"
    assert first_week[6] is not None
    assert first_week[6].entry.day_name == "Saturday"


def test_day_detail_all_groups_comparison():
    """Day detail compares all 4 groups and detects Kuwaiti holidays."""
    detail = get_day_detail(date(2026, 2, 25), "KNPC", "B", today=date(2026, 2, 20))
    assert detail.entry.holiday == "National Day"
    assert len(detail.all_groups) == 4
    selected = [g for g in detail.all_groups if g.is_selected]
    assert len(selected) == 1
    assert selected[0].group == "B"


def test_resolve_date_range_validation():
    """Invalid custom date bounds return friendly errors without raising."""
    today = date(2026, 11, 22)
    s, e, key, err = resolve_date_range("week", None, None, today)
    assert key == "week"
    assert err is None
    assert (e - s).days == 7

    _, _, key_bad, err_bad = resolve_date_range("custom", "2026-12-10", "2026-12-01", today)
    assert key_bad == "custom"
    assert err_bad is not None

    _, _, key_span, err_span = resolve_date_range("custom", "2020-01-01", "2035-01-01", today)
    assert key_span == "custom"
    assert err_span is not None


def test_export_csv_and_ics():
    """CSV and ICS exporters emit valid structured payloads."""
    result = build_schedule("KNPC", "A", date(2026, 2, 24), date(2026, 2, 26), today=date(2026, 2, 24))

    csv_text = export_csv(result.entries)
    lines = csv_text.strip().splitlines()
    assert lines[0] == "Date,Day of Week,Shift,Holiday"
    assert len(lines) == 4
    assert "2026-02-25,Wednesday," in lines[2]
    assert "National Day" in lines[2]

    ics_text = export_ics(result.entries, "KNPC", "A")
    assert "BEGIN:VCALENDAR" in ics_text
    assert "END:VCALENDAR" in ics_text
    assert "SUMMARY:Kuwait Holiday: National Day" in ics_text
    assert "DTSTART;VALUE=DATE:20260225" in ics_text
