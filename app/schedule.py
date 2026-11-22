"""Pure domain logic for KNPC and KOC shift schedules and Kuwaiti holidays."""

from __future__ import annotations

import calendar
import csv
import io
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays

EPOCH_DATE = date(2024, 10, 6)
MIN_DATE = date(2020, 1, 1)
MAX_DATE = date(2050, 12, 31)
MAX_SPAN_DAYS = 1830

COMPANIES: tuple[str, ...] = ("KNPC", "KOC")
GROUPS: tuple[str, ...] = ("A", "B", "C", "D")
SHIFTS: tuple[str, ...] = ("Morning", "Afternoon", "Night", "Off")
WEEKDAY_HEADERS: tuple[str, ...] = ("Su", "Mo", "Tu", "We", "Th", "Fr", "Sa")

SHIFT_CYCLES: dict[tuple[str, str], tuple[str, ...]] = {
    ("KNPC", "A"): ("Night", "Night", "Off", "Off", "Morning", "Morning", "Afternoon", "Afternoon"),
    ("KNPC", "B"): ("Morning", "Morning", "Afternoon", "Afternoon", "Night", "Night", "Off", "Off"),
    ("KNPC", "C"): ("Off", "Off", "Morning", "Morning", "Afternoon", "Afternoon", "Night", "Night"),
    ("KNPC", "D"): ("Afternoon", "Afternoon", "Night", "Night", "Off", "Off", "Morning", "Morning"),
    ("KOC", "A"): ("Night", "Off", "Off", "Morning"),
    ("KOC", "B"): ("Off", "Off", "Morning", "Night"),
    ("KOC", "C"): ("Off", "Morning", "Night", "Off"),
    ("KOC", "D"): ("Morning", "Night", "Off", "Off"),
}

QUICK_RANGES: dict[str, tuple[str, int | None]] = {
    "year": ("Next Year", 365),
    "week": ("Next Week", 7),
    "month": ("Next Month", 30),
    "3months": ("Next 3 Months", 90),
    "6months": ("Next 6 Months", 180),
    "custom": ("Custom", None),
}

SHIFT_META: dict[str, dict[str, str]] = {
    "Morning": {
        "short": "M",
        "form_short": "M",
        "cell_class": "shift-morning",
        "badge_class": "shift-badge-morning",
        "row_class": "shift-row-morning",
        "dot_class": "shift-dot-morning",
        "form_class": "shift-form-morning",
    },
    "Afternoon": {
        "short": "A",
        "form_short": "A",
        "cell_class": "shift-afternoon",
        "badge_class": "shift-badge-afternoon",
        "row_class": "shift-row-afternoon",
        "dot_class": "shift-dot-afternoon",
        "form_class": "shift-form-afternoon",
    },
    "Night": {
        "short": "N",
        "form_short": "N",
        "cell_class": "shift-night",
        "badge_class": "shift-badge-night",
        "row_class": "shift-row-night",
        "dot_class": "shift-dot-night",
        "form_class": "shift-form-night",
    },
    "Off": {
        "short": "OFF",
        "form_short": "OFF",
        "cell_class": "shift-off",
        "badge_class": "shift-badge-off",
        "row_class": "shift-row-off",
        "dot_class": "shift-dot-off",
        "form_class": "shift-form-off",
    },
}

# (start_hour, start_min, end_hour, end_min, end_day_offset) in Asia/Kuwait (UTC+3)
SHIFT_TIMES: dict[str, tuple[int, int, int, int, int]] = {
    "Morning": (6, 0, 14, 0, 0),
    "Afternoon": (14, 0, 22, 0, 0),
    "Night": (22, 0, 6, 0, 1),
}


@dataclass(frozen=True, slots=True)
class DayEntry:
    """Single day in a computed schedule."""

    date: date
    iso: str
    formatted_date: str
    day_name: str
    short_day: str
    shift: str
    shift_short: str
    holiday: str
    is_today: bool
    is_weekend_day: bool
    is_long_weekend: bool


@dataclass(frozen=True, slots=True)
class LongWeekend:
    """Consecutive Friday and Saturday where both days are Off."""

    friday: DayEntry
    saturday: DayEntry
    days_away: int
    holidays: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MonthCell:
    """Single cell inside a Sunday-first monthly calendar grid."""

    day_num: int
    entry: DayEntry
    in_range: bool


@dataclass(frozen=True, slots=True)
class MonthGrid:
    """Sunday-first calendar grid for a single month."""

    year: int
    month: int
    month_key: str
    label: str
    short_label: str
    weeks: tuple[tuple[MonthCell | None, ...], ...]
    long_weekend_count: int
    holiday_count: int


@dataclass(frozen=True, slots=True)
class ScheduleSummary:
    """Aggregate shift and milestone counts for a schedule range."""

    total_days: int
    morning_days: int
    afternoon_days: int
    night_days: int
    off_days: int
    holiday_count: int
    long_weekend_count: int


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    """Complete schedule payload consumed by templates and exporters."""

    company: str
    group: str
    start_date: date
    end_date: date
    today: date
    entries: tuple[DayEntry, ...]
    long_weekends: tuple[LongWeekend, ...]
    holidays_list: tuple[DayEntry, ...]
    month_grids: tuple[MonthGrid, ...]
    summary: ScheduleSummary
    today_entry: DayEntry
    tomorrow_entry: DayEntry
    next_8_days: tuple[DayEntry, ...]
    next_off_date: date | None
    days_until_off: int | None
    next_long_weekend: LongWeekend | None


@dataclass(frozen=True, slots=True)
class GroupShiftComparison:
    """Shift assignment for a single group on an inspected date."""

    group: str
    shift: str
    shift_short: str
    cycle_day: int
    cycle_length: int
    is_selected: bool


@dataclass(frozen=True, slots=True)
class DayDetail:
    """Detailed modal payload for a single inspected date."""

    company: str
    group: str
    entry: DayEntry
    cycle_day: int
    cycle_length: int
    all_groups: tuple[GroupShiftComparison, ...]


def kuwait_today() -> date:
    """Return today's calendar date in Asia/Kuwait (UTC+3)."""
    try:
        return datetime.now(ZoneInfo("Asia/Kuwait")).date()
    except ZoneInfoNotFoundError:
        return datetime.now(timezone(timedelta(hours=3))).date()


@lru_cache(maxsize=64)
def get_kuwait_holidays(year: int) -> dict[date, str]:
    """Return cached official Kuwaiti holidays for a given year."""
    try:
        kw = holidays.country_holidays("KW", years=[year], language="en_US")
        return {holiday_date: str(name) for holiday_date, name in kw.items()}
    except (KeyError, ValueError, NotImplementedError):
        return {}


def get_holiday_name(target_date: date) -> str:
    """Return official Kuwaiti holiday name for target_date, or empty string."""
    return get_kuwait_holidays(target_date.year).get(target_date, "")


def normalize_company(value: str | None) -> str:
    """Normalize company input to KNPC or KOC."""
    if value and value.strip().upper() == "KOC":
        return "KOC"
    return "KNPC"


def normalize_group(value: str | None) -> str:
    """Normalize group input to A, B, C, or D."""
    if value:
        candidate = value.strip().upper()
        if candidate in GROUPS:
            return candidate
    return "A"


def get_shift_for_date(target_date: date, company: str, group: str) -> str:
    """Return shift type for target_date based on deterministic epoch cycle."""
    cycle = SHIFT_CYCLES[(company, group)]
    days_since_epoch = (target_date - EPOCH_DATE).days
    return cycle[days_since_epoch % len(cycle)]


def get_cycle_position(target_date: date, company: str, group: str) -> tuple[int, int]:
    """Return 1-indexed (day_in_cycle, cycle_length) for target_date."""
    cycle = SHIFT_CYCLES[(company, group)]
    days_since_epoch = (target_date - EPOCH_DATE).days
    index = days_since_epoch % len(cycle)
    return index + 1, len(cycle)


def format_countdown(days_away: int) -> str:
    """Format day delta as a friendly human label."""
    if days_away == 0:
        return "Today"
    if days_away == 1:
        return "Tomorrow"
    if days_away > 1:
        return f"In {days_away} days"
    days_ago = abs(days_away)
    return "Yesterday" if days_ago == 1 else f"{days_ago} days ago"


def _parse_iso_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def resolve_date_range(
    range_key: str | None,
    start_str: str | None,
    end_str: str | None,
    today: date,
) -> tuple[date, date, str, str | None]:
    """Resolve and validate date range from quick-select preset or custom bounds."""
    key = (range_key or "year").strip().lower()
    if key not in QUICK_RANGES:
        key = "year"

    if key != "custom":
        _, delta_days = QUICK_RANGES[key]
        assert delta_days is not None
        start_d = max(MIN_DATE, min(today, MAX_DATE))
        end_d = min(MAX_DATE, start_d + timedelta(days=delta_days))
        return start_d, end_d, key, None

    default_start = max(MIN_DATE, min(today, MAX_DATE))
    default_end = min(MAX_DATE, default_start + timedelta(days=365))

    if not start_str and not end_str:
        return default_start, default_end, "custom", None

    parsed_start = _parse_iso_date(start_str)
    parsed_end = _parse_iso_date(end_str)

    if parsed_start is None or parsed_end is None:
        return (
            default_start,
            default_end,
            "custom",
            "Please select both a valid start date and end date.",
        )

    if parsed_start < MIN_DATE or parsed_end > MAX_DATE:
        return (
            default_start,
            default_end,
            "custom",
            f"Dates must stay between {MIN_DATE.isoformat()} and {MAX_DATE.isoformat()}.",
        )

    if parsed_start > parsed_end:
        return (
            default_start,
            default_end,
            "custom",
            "Start date must be on or before the end date.",
        )

    if (parsed_end - parsed_start).days > MAX_SPAN_DAYS:
        return (
            default_start,
            default_end,
            "custom",
            "Custom range cannot exceed 5 years (1,830 days). Showing the next year instead.",
        )

    return parsed_start, parsed_end, "custom", None


def _is_part_of_long_weekend(target_date: date, company: str, group: str) -> bool:
    """Return True if target_date is Friday or Saturday of a consecutive Fri+Sat Off pair."""
    weekday = target_date.weekday()
    if weekday == 4:
        return (
            get_shift_for_date(target_date, company, group) == "Off"
            and get_shift_for_date(target_date + timedelta(days=1), company, group) == "Off"
        )
    if weekday == 5:
        return (
            get_shift_for_date(target_date - timedelta(days=1), company, group) == "Off"
            and get_shift_for_date(target_date, company, group) == "Off"
        )
    return False


def _make_day_entry(
    target_date: date,
    company: str,
    group: str,
    today: date,
    *,
    is_long_weekend: bool | None = None,
) -> DayEntry:
    shift = get_shift_for_date(target_date, company, group)
    holiday = get_holiday_name(target_date)
    weekday = target_date.weekday()
    lw = (
        _is_part_of_long_weekend(target_date, company, group)
        if is_long_weekend is None
        else is_long_weekend
    )
    return DayEntry(
        date=target_date,
        iso=target_date.isoformat(),
        formatted_date=target_date.strftime("%d %B %Y"),
        day_name=target_date.strftime("%A"),
        short_day=target_date.strftime("%a"),
        shift=shift,
        shift_short=SHIFT_META[shift]["short"],
        holiday=holiday,
        is_today=(target_date == today),
        is_weekend_day=(weekday in (4, 5)),
        is_long_weekend=lw,
    )


def find_long_weekends(entries: list[DayEntry], today: date) -> tuple[list[LongWeekend], set[date]]:
    """Find consecutive Friday + Saturday Off pairs inside entries."""
    long_weekends: list[LongWeekend] = []
    lw_dates: set[date] = set()

    for idx in range(len(entries) - 1):
        curr = entries[idx]
        nxt = entries[idx + 1]
        if (
            curr.date.weekday() == 4
            and nxt.date == curr.date + timedelta(days=1)
            and curr.shift == "Off"
            and nxt.shift == "Off"
        ):
            lw_dates.add(curr.date)
            lw_dates.add(nxt.date)
            pair_holidays = tuple(h for h in (curr.holiday, nxt.holiday) if h)
            long_weekends.append(
                LongWeekend(
                    friday=curr,
                    saturday=nxt,
                    days_away=(curr.date - today).days,
                    holidays=pair_holidays,
                )
            )
    return long_weekends, lw_dates


def _iter_month_starts(start_date: date, end_date: date) -> list[tuple[int, int]]:
    months: list[tuple[int, int]] = []
    year, month = start_date.year, start_date.month
    while (year, month) <= (end_date.year, end_date.month):
        months.append((year, month))
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return months


def _build_month_grid(
    cal: calendar.Calendar,
    year: int,
    month: int,
    company: str,
    group: str,
    today: date,
    entries_by_date: dict[date, DayEntry] | None = None,
) -> MonthGrid:
    """Build a single Sunday-first MonthGrid."""
    weeks: list[tuple[MonthCell | None, ...]] = []
    lw_fridays = 0
    holiday_count = 0

    for week in cal.monthdatescalendar(year, month):
        cells: list[MonthCell | None] = []
        for cell_date in week:
            if cell_date.month != month:
                cells.append(None)
                continue
            if entries_by_date is not None:
                entry = entries_by_date.get(cell_date)
                in_range = entry is not None
                if entry is None:
                    entry = _make_day_entry(cell_date, company, group, today)
            else:
                entry = _make_day_entry(cell_date, company, group, today)
                in_range = True
            if in_range:
                if entry.is_long_weekend and cell_date.weekday() == 4:
                    lw_fridays += 1
                if entry.holiday:
                    holiday_count += 1
            cells.append(MonthCell(day_num=cell_date.day, entry=entry, in_range=in_range))
        weeks.append(tuple(cells))

    first_day = date(year, month, 1)
    return MonthGrid(
        year=year,
        month=month,
        month_key=f"{year:04d}-{month:02d}",
        label=first_day.strftime("%B %Y"),
        short_label=first_day.strftime("%b %Y"),
        weeks=tuple(weeks),
        long_weekend_count=lw_fridays,
        holiday_count=holiday_count,
    )


def build_single_month_grid(
    company: str,
    group: str,
    year: int,
    month: int,
    today: date | None = None,
) -> MonthGrid:
    """Build a standalone Sunday-first MonthGrid for any year/month."""
    cal = calendar.Calendar(firstweekday=6)
    return _build_month_grid(
        cal,
        year,
        month,
        normalize_company(company),
        normalize_group(group),
        today or kuwait_today(),
    )


def build_month_grids(
    entries_by_date: dict[date, DayEntry],
    company: str,
    group: str,
    start_date: date,
    end_date: date,
    today: date,
) -> tuple[MonthGrid, ...]:
    """Build Sunday-first month grids for every month spanned by [start_date, end_date]."""
    cal = calendar.Calendar(firstweekday=6)
    return tuple(
        _build_month_grid(cal, year, month, company, group, today, entries_by_date)
        for year, month in _iter_month_starts(start_date, end_date)
    )


def _find_next_off(company: str, group: str, today: date) -> tuple[date | None, int | None]:
    for offset in range(12):
        candidate = today + timedelta(days=offset)
        if get_shift_for_date(candidate, company, group) == "Off":
            return candidate, offset
    return None, None


def _find_next_long_weekend(company: str, group: str, today: date) -> LongWeekend | None:
    """Scan forward up to 90 days from today for the next Fri+Sat Off weekend."""
    lookahead = [
        _make_day_entry(today + timedelta(days=offset), company, group, today, is_long_weekend=False)
        for offset in range(91)
    ]
    upcoming, _ = find_long_weekends(lookahead, today)
    return upcoming[0] if upcoming else None


def build_schedule(
    company: str,
    group: str,
    start_date: date,
    end_date: date,
    today: date | None = None,
) -> ScheduleResult:
    """Build complete schedule, summaries, holidays, long weekends, and calendar grids."""
    ref_today = today or kuwait_today()
    norm_company = normalize_company(company)
    norm_group = normalize_group(group)

    raw_entries: list[DayEntry] = []
    current = start_date
    while current <= end_date:
        raw_entries.append(
            _make_day_entry(current, norm_company, norm_group, ref_today, is_long_weekend=False)
        )
        current += timedelta(days=1)

    _, lw_dates = find_long_weekends(raw_entries, ref_today)

    entries = [
        DayEntry(
            date=e.date,
            iso=e.iso,
            formatted_date=e.formatted_date,
            day_name=e.day_name,
            short_day=e.short_day,
            shift=e.shift,
            shift_short=e.shift_short,
            holiday=e.holiday,
            is_today=e.is_today,
            is_weekend_day=e.is_weekend_day,
            is_long_weekend=(e.date in lw_dates),
        )
        for e in raw_entries
    ]

    long_weekends, _ = find_long_weekends(entries, ref_today)
    holidays_list = tuple(e for e in entries if e.holiday)
    entries_by_date = {e.date: e for e in entries}
    month_grids = build_month_grids(
        entries_by_date,
        norm_company,
        norm_group,
        start_date,
        end_date,
        ref_today,
    )

    counts = {shift: 0 for shift in SHIFTS}
    for entry in entries:
        counts[entry.shift] += 1

    summary = ScheduleSummary(
        total_days=len(entries),
        morning_days=counts["Morning"],
        afternoon_days=counts["Afternoon"],
        night_days=counts["Night"],
        off_days=counts["Off"],
        holiday_count=len(holidays_list),
        long_weekend_count=len(long_weekends),
    )

    next_8_days = tuple(
        _make_day_entry(ref_today + timedelta(days=offset), norm_company, norm_group, ref_today)
        for offset in range(8)
    )
    today_entry = next_8_days[0]
    tomorrow_entry = next_8_days[1]
    next_off_date, days_until_off = _find_next_off(norm_company, norm_group, ref_today)
    next_lw = _find_next_long_weekend(norm_company, norm_group, ref_today)

    return ScheduleResult(
        company=norm_company,
        group=norm_group,
        start_date=start_date,
        end_date=end_date,
        today=ref_today,
        entries=tuple(entries),
        long_weekends=tuple(long_weekends),
        holidays_list=holidays_list,
        month_grids=month_grids,
        summary=summary,
        today_entry=today_entry,
        tomorrow_entry=tomorrow_entry,
        next_8_days=next_8_days,
        next_off_date=next_off_date,
        days_until_off=days_until_off,
        next_long_weekend=next_lw,
    )


def get_day_detail(
    target_date: date,
    company: str,
    group: str,
    today: date | None = None,
) -> DayDetail:
    """Build full day detail including cycle day and all-group comparison."""
    ref_today = today or kuwait_today()
    norm_company = normalize_company(company)
    norm_group = normalize_group(group)

    entry = _make_day_entry(target_date, norm_company, norm_group, ref_today)
    cycle_day, cycle_length = get_cycle_position(target_date, norm_company, norm_group)

    comparisons: list[GroupShiftComparison] = []
    for grp in GROUPS:
        grp_shift = get_shift_for_date(target_date, norm_company, grp)
        grp_cycle_day, grp_cycle_len = get_cycle_position(target_date, norm_company, grp)
        comparisons.append(
            GroupShiftComparison(
                group=grp,
                shift=grp_shift,
                shift_short=SHIFT_META[grp_shift]["short"],
                cycle_day=grp_cycle_day,
                cycle_length=grp_cycle_len,
                is_selected=(grp == norm_group),
            )
        )

    return DayDetail(
        company=norm_company,
        group=norm_group,
        entry=entry,
        cycle_day=cycle_day,
        cycle_length=cycle_length,
        all_groups=tuple(comparisons),
    )


def export_csv(entries: tuple[DayEntry, ...] | list[DayEntry]) -> str:
    """Export schedule entries as UTF-8 CSV matching legacy column layout."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["Date", "Day of Week", "Shift", "Holiday"])
    for entry in entries:
        writer.writerow([entry.iso, entry.day_name, entry.shift, entry.holiday])
    return buf.getvalue()


def _ics_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def export_ics(
    entries: tuple[DayEntry, ...] | list[DayEntry],
    company: str,
    group: str,
) -> str:
    """Export schedule entries and Kuwaiti holidays as an RFC 5545 iCalendar feed."""
    norm_company = normalize_company(company)
    norm_group = normalize_group(group)
    dtstamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//KNPC Schedule//Shift Calendar//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(f'{norm_company} Group {norm_group} Schedule')}",
        "X-WR-TIMEZONE:Asia/Kuwait",
        "BEGIN:VTIMEZONE",
        "TZID:Asia/Kuwait",
        "BEGIN:STANDARD",
        "DTSTART:19700101T000000",
        "TZOFFSETFROM:+0300",
        "TZOFFSETTO:+0300",
        "TZNAME:AST",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]

    for entry in entries:
        start_compact = entry.date.strftime("%Y%m%d")
        end_compact = (entry.date + timedelta(days=1)).strftime("%Y%m%d")
        shift_summary = f"{norm_company} {norm_group}: {entry.shift}"
        if entry.is_long_weekend:
            shift_summary += " (Long Weekend)"

        if entry.shift in SHIFT_TIMES:
            sh, sm, eh, em, end_offset = SHIFT_TIMES[entry.shift]
            end_date_str = (entry.date + timedelta(days=end_offset)).strftime("%Y%m%d")
            dtstart_line = f"DTSTART;TZID=Asia/Kuwait:{start_compact}T{sh:02d}{sm:02d}00"
            dtend_line = f"DTEND;TZID=Asia/Kuwait:{end_date_str}T{eh:02d}{em:02d}00"
            transp_line = "TRANSP:OPAQUE"
        else:
            dtstart_line = f"DTSTART;VALUE=DATE:{start_compact}"
            dtend_line = f"DTEND;VALUE=DATE:{end_compact}"
            transp_line = "TRANSP:TRANSPARENT"

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:shift-{norm_company.lower()}-{norm_group.lower()}-{start_compact}@knpc-schedule",
                f"DTSTAMP:{dtstamp}",
                dtstart_line,
                dtend_line,
                f"SUMMARY:{_ics_escape(shift_summary)}",
                transp_line,
                "END:VEVENT",
            ]
        )

        if entry.holiday:
            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:holiday-kw-{start_compact}@knpc-schedule",
                    f"DTSTAMP:{dtstamp}",
                    f"DTSTART;VALUE=DATE:{start_compact}",
                    f"DTEND;VALUE=DATE:{end_compact}",
                    f"SUMMARY:{_ics_escape(f'Kuwait Holiday: {entry.holiday}')}",
                    "TRANSP:TRANSPARENT",
                    "END:VEVENT",
                ]
            )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
