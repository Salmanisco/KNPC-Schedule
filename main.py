"""FastAPI entrypoint for the KNPC Schedule web application."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.schedule import (
    COMPANIES,
    GROUPS,
    MAX_DATE,
    MIN_DATE,
    QUICK_RANGES,
    SHIFT_META,
    WEEKDAY_HEADERS,
    build_schedule,
    build_single_month_grid,
    export_csv,
    export_ics,
    format_countdown,
    get_day_detail,
    kuwait_today,
    normalize_company,
    normalize_group,
    resolve_date_range,
)

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "public" / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
_APP_CSS = STATIC_DIR / "css" / "app.css"
CSS_VERSION = (
    hashlib.md5(_APP_CSS.read_bytes(), usedforsecurity=False).hexdigest()[:8]
    if _APP_CSS.is_file()
    else "1"
)

VALID_VIEWS = ("calendar", "weekends", "holidays", "schedule")
VALID_SHIFT_FILTERS = ("all", "Morning", "Afternoon", "Night", "Off", "holiday")
PREF_COOKIE_NAME = "knpc_pref"

app = FastAPI(title="KNPC Schedule", docs_url=None, redoc_url=None, openapi_url=None)

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["SHIFT_META"] = SHIFT_META
templates.env.globals["COMPANIES"] = COMPANIES
templates.env.globals["GROUPS"] = GROUPS
templates.env.globals["QUICK_RANGES"] = QUICK_RANGES
templates.env.globals["WEEKDAY_HEADERS"] = WEEKDAY_HEADERS
templates.env.globals["MIN_DATE_ISO"] = MIN_DATE.isoformat()
templates.env.globals["MAX_DATE_ISO"] = MAX_DATE.isoformat()
templates.env.globals["CSS_VERSION"] = CSS_VERSION
templates.env.globals["format_countdown"] = format_countdown
templates.env.globals["MONTH_NAMES"] = (
    (1, "January"),
    (2, "February"),
    (3, "March"),
    (4, "April"),
    (5, "May"),
    (6, "June"),
    (7, "July"),
    (8, "August"),
    (9, "September"),
    (10, "October"),
    (11, "November"),
    (12, "December"),
)
templates.env.globals["CALENDAR_YEARS"] = tuple(range(MIN_DATE.year, MAX_DATE.year + 1))


def _parse_pref_cookie(cookie_value: str | None) -> tuple[str | None, str | None, str | None]:
    if not cookie_value or ":" not in cookie_value:
        return None, None, None
    parts = cookie_value.split(":", 2)
    company = parts[0].strip().upper()
    group = parts[1].strip().upper()
    if company not in COMPANIES or group not in GROUPS:
        return None, None, None
    saved_range: str | None = None
    if len(parts) == 3:
        candidate_range = parts[2].strip().lower()
        if candidate_range in QUICK_RANGES and candidate_range != "custom":
            saved_range = candidate_range
    return company, group, saved_range


def _build_query_url(base: str = "/", **params: str | None) -> str:
    clean = {k: v for k, v in params.items() if v is not None and v != ""}
    if not clean:
        return base
    return f"{base}?{urlencode(clean)}"


templates.env.globals["build_query_url"] = _build_query_url


def _resolve_company_group(
    request: Request,
    company: str | None,
    group: str | None,
) -> tuple[str, str]:
    cookie_company, cookie_group, _ = _parse_pref_cookie(request.cookies.get(PREF_COOKIE_NAME))
    resolved_company = normalize_company(company or cookie_company)
    resolved_group = normalize_group(group or cookie_group)
    return resolved_company, resolved_group


def _normalize_view(value: str | None) -> str:
    if value and value.strip().lower() in VALID_VIEWS:
        return value.strip().lower()
    return "calendar"


def _normalize_shift_filter(value: str | None) -> str:
    if value and value.strip() in VALID_SHIFT_FILTERS:
        return value.strip()
    return "all"


def _resolve_target_month(
    today: date,
    month_str: str | None,
    cal_year: int | None,
    cal_month: int | None,
) -> tuple[int, int]:
    target_year = today.year
    target_month = today.month
    if month_str and "-" in month_str:
        parts = month_str.split("-", 1)
        if parts[0].isdigit() and parts[1].isdigit():
            target_year = int(parts[0])
            target_month = int(parts[1])
    if cal_year is not None:
        target_year = cal_year
    if cal_month is not None:
        target_month = cal_month
    target_year = max(MIN_DATE.year, min(MAX_DATE.year, target_year))
    target_month = max(1, min(12, target_month))
    return target_year, target_month


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    company: str | None = Query(default=None),
    group: str | None = Query(default=None),
    range_key: str | None = Query(default=None, alias="range"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    view: str | None = Query(default="calendar"),
    month: str | None = Query(default=None),
    cal_year: int | None = Query(default=None),
    cal_month: int | None = Query(default=None),
    shift_filter: str | None = Query(default="all"),
    save: bool = Query(default=False),
) -> HTMLResponse:
    """Render full page or HTMX partial workspace/view panel."""
    today = kuwait_today()
    saved_company, saved_group, saved_range = _parse_pref_cookie(
        request.cookies.get(PREF_COOKIE_NAME)
    )
    has_saved_pref = saved_company is not None

    resolved_company = normalize_company(company or saved_company)
    resolved_group = normalize_group(group or saved_group)
    effective_range_input = range_key or saved_range or "year"

    start_d, end_d, norm_range, range_error = resolve_date_range(
        effective_range_input, start, end, today
    )
    norm_view = _normalize_view(view)
    norm_filter = _normalize_shift_filter(shift_filter)

    is_shared_override = bool(
        has_saved_pref
        and (company is not None or group is not None)
        and not save
        and (resolved_company != saved_company or resolved_group != saved_group)
    )
    should_set_cookie = bool(save)

    cookie_range = norm_range if norm_range != "custom" else (saved_range or "year")
    if should_set_cookie:
        has_saved_pref = True
        saved_company = resolved_company
        saved_group = resolved_group
        saved_range = cookie_range

    schedule = build_schedule(
        company=resolved_company,
        group=resolved_group,
        start_date=start_d,
        end_date=end_d,
        today=today,
    )

    target_year, target_month = _resolve_target_month(today, month, cal_year, cal_month)
    active_month_grid = build_single_month_grid(
        resolved_company, resolved_group, target_year, target_month, today=today
    )
    if (target_year, target_month) > (MIN_DATE.year, 1):
        py, pm = (target_year - 1, 12) if target_month == 1 else (target_year, target_month - 1)
        prev_month_key: str | None = f"{py:04d}-{pm:02d}"
    else:
        prev_month_key = None
    if (target_year, target_month) < (MAX_DATE.year, 12):
        ny, nm = (target_year + 1, 1) if target_month == 12 else (target_year, target_month + 1)
        next_month_key: str | None = f"{ny:04d}-{nm:02d}"
    else:
        next_month_key = None
    is_current_month = (target_year == today.year and target_month == today.month)

    if norm_filter == "holiday":
        filtered_entries = tuple(e for e in schedule.entries if e.holiday)
    elif norm_filter != "all":
        filtered_entries = tuple(e for e in schedule.entries if e.shift == norm_filter)
    else:
        filtered_entries = schedule.entries

    base_params: dict[str, str] = {
        "company": resolved_company,
        "group": resolved_group,
        "range": norm_range,
        "view": norm_view,
    }
    if norm_range == "custom":
        base_params["start"] = start_d.isoformat()
        base_params["end"] = end_d.isoformat()
    if norm_view == "calendar" and not is_current_month:
        base_params["month"] = active_month_grid.month_key
    if norm_filter != "all":
        base_params["shift_filter"] = norm_filter

    context = {
        "schedule": schedule,
        "company": resolved_company,
        "group": resolved_group,
        "range_key": norm_range,
        "start_iso": start_d.isoformat(),
        "end_iso": end_d.isoformat(),
        "start_display": start_d.strftime("%d %b %Y"),
        "end_display": end_d.strftime("%d %b %Y"),
        "range_error": range_error,
        "view": norm_view,
        "cal_year": target_year,
        "cal_month": target_month,
        "is_current_month": is_current_month,
        "active_month_grid": active_month_grid,
        "active_month_key": active_month_grid.month_key,
        "prev_month_key": prev_month_key,
        "next_month_key": next_month_key,
        "shift_filter": norm_filter,
        "filtered_entries": filtered_entries,
        "base_params": base_params,
        "has_saved_pref": has_saved_pref,
        "saved_company": saved_company,
        "saved_group": saved_group,
        "saved_range": saved_range or "year",
        "is_shared_override": is_shared_override,
        "just_saved": should_set_cookie,
    }

    is_htmx = request.headers.get("HX-Request") == "true"
    hx_target = request.headers.get("HX-Target", "")
    if is_htmx and hx_target == "view-panel":
        template_name = "partials/view_panel.html"
        oob_nav = True
        oob_settings = False
    elif is_htmx:
        template_name = "partials/workspace.html"
        oob_nav = True
        oob_settings = True
    else:
        template_name = "index.html"
        oob_nav = False
        oob_settings = False

    context["oob_nav"] = oob_nav
    context["oob_settings"] = oob_settings

    response = templates.TemplateResponse(request=request, name=template_name, context=context)
    response.headers["Vary"] = "HX-Request, Cookie"
    response.headers["Cache-Control"] = "private, no-cache"
    if is_htmx:
        response.headers["HX-Push-Url"] = _build_query_url("/", **base_params)

    if should_set_cookie:
        response.set_cookie(
            key=PREF_COOKIE_NAME,
            value=f"{resolved_company}:{resolved_group}:{cookie_range}",
            max_age=31536000,
            samesite="lax",
            httponly=False,
        )

    return response


@app.get("/day/{iso_date}", response_class=HTMLResponse)
async def day_detail(
    request: Request,
    iso_date: str,
    company: str | None = Query(default=None),
    group: str | None = Query(default=None),
) -> HTMLResponse:
    """Return modal content inspecting a single calendar date."""
    try:
        target_date = date.fromisoformat(iso_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid date format.") from exc

    if target_date < MIN_DATE or target_date > MAX_DATE:
        raise HTTPException(status_code=400, detail="Date out of supported range.")

    today = kuwait_today()
    resolved_company, resolved_group = _resolve_company_group(request, company, group)
    detail = get_day_detail(target_date, resolved_company, resolved_group, today=today)

    response = templates.TemplateResponse(
        request=request,
        name="partials/day_dialog.html",
        context={"detail": detail},
    )
    response.headers["Cache-Control"] = "private, no-cache"
    return response


@app.get("/export/csv")
async def download_csv(
    request: Request,
    company: str | None = Query(default=None),
    group: str | None = Query(default=None),
    range_key: str | None = Query(default="year", alias="range"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> Response:
    """Download selected schedule range as CSV."""
    today = kuwait_today()
    resolved_company, resolved_group = _resolve_company_group(request, company, group)
    start_d, end_d, _, _ = resolve_date_range(range_key, start, end, today)
    schedule = build_schedule(resolved_company, resolved_group, start_d, end_d, today=today)
    csv_body = export_csv(schedule.entries)
    filename = f"{resolved_company}_{resolved_group}_schedule.csv"
    return Response(
        content=csv_body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/ics")
async def download_ics(
    request: Request,
    company: str | None = Query(default=None),
    group: str | None = Query(default=None),
    range_key: str | None = Query(default="year", alias="range"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> Response:
    """Download selected schedule range and Kuwaiti holidays as an iCalendar (.ics) file."""
    today = kuwait_today()
    resolved_company, resolved_group = _resolve_company_group(request, company, group)
    start_d, end_d, _, _ = resolve_date_range(range_key, start, end, today)
    schedule = build_schedule(resolved_company, resolved_group, start_d, end_d, today=today)
    ics_body = export_ics(schedule.entries, resolved_company, resolved_group)
    filename = f"{resolved_company}_{resolved_group}_schedule.ics"
    return Response(
        content=ics_body,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/sw.js")
async def service_worker() -> FileResponse:
    """Serve PWA service worker with no-cache headers for local and container runs."""
    return FileResponse(
        BASE_DIR / "public" / "sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Lightweight health check endpoint for PaaS probes."""
    return {"status": "ok"}
