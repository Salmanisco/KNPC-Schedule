"""Integration tests for FastAPI routes, HTMX partials, cookies, and static assets."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_full_page_load_and_headers():
    """GET / returns complete HTML shell with Vary and Cache-Control guards."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text
    assert "KNPC Schedule" in resp.text
    assert resp.headers.get("vary") == "HX-Request, Cookie"
    assert resp.headers.get("cache-control") == "private, no-cache"


def test_htmx_workspace_swap_and_preference_cookie():
    """HX-Request returns workspace partial and remembers preference cookie."""
    resp = client.get(
        "/?company=KOC&group=B&view=weekends",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in resp.text
    assert "Long Weekends" in resp.text
    assert "KOC" in resp.text
    assert resp.cookies.get("knpc_pref") == "KOC:B"

    # Follow-up request with cookie defaults to KOC B
    resp_cookie = client.get("/", cookies={"knpc_pref": "KOC:B"})
    assert resp_cookie.status_code == 200
    assert "Today &middot; KOC B" in resp_cookie.text

    # Explicit query params override cookie
    resp_override = client.get("/?company=KNPC&group=D", cookies={"knpc_pref": "KOC:B"})
    assert resp_override.status_code == 200
    assert "Today &middot; KNPC D" in resp_override.text


def test_htmx_view_panel_all_views_and_calendar_modes():
    """HX-Target=view-panel renders view fragment + OOB form sync across all views."""
    for view in ("calendar", "weekends", "holidays", "schedule"):
        resp = client.get(
            f"/?company=KNPC&group=A&view={view}",
            headers={"HX-Request": "true", "HX-Target": "view-panel"},
        )
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert 'id="form-state-sync" hx-swap-oob="true"' in resp.text

    for cal_mode in ("year", "month", "list"):
        resp = client.get(
            f"/?company=KNPC&group=C&view=calendar&cal_mode={cal_mode}",
            headers={"HX-Request": "true", "HX-Target": "view-panel"},
        )
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text


def test_invalid_custom_date_range_shows_alert():
    """Start date after end date renders a clean error alert without crashing."""
    resp = client.get("/?company=KNPC&group=A&range=custom&start=2026-12-20&end=2026-12-01")
    assert resp.status_code == 200
    assert "Start date must be on or before the end date." in resp.text


def test_day_detail_modal_endpoint():
    """GET /day/{iso} renders holiday info and 4-group comparison."""
    resp = client.get("/day/2026-02-25?company=KNPC&group=A")
    assert resp.status_code == 200
    assert "National Day" in resp.text
    assert "All KNPC Groups on This Day" in resp.text

    bad_resp = client.get("/day/not-a-date")
    assert bad_resp.status_code == 400


def test_exports_and_health_and_static_assets():
    """CSV, ICS, /health, and static files all return expected content."""
    csv_resp = client.get("/export/csv?company=KOC&group=D&range=week")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert 'filename="KOC_D_schedule.csv"' in csv_resp.headers["content-disposition"]
    assert "Date,Day of Week,Shift,Holiday" in csv_resp.text

    ics_resp = client.get("/export/ics?company=KNPC&group=A&range=month")
    assert ics_resp.status_code == 200
    assert ics_resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in ics_resp.text

    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    for asset in (
        "/static/css/app.css",
        "/static/js/htmx.min.js",
        "/static/img/logo.png",
        "/static/img/favicon.png",
        "/static/manifest.webmanifest",
    ):
        asset_resp = client.get(asset)
        assert asset_resp.status_code == 200, f"Failed asset: {asset}"
