"""Integration tests for FastAPI routes, mobile PWA shell, HTMX partials, and saved prefs."""

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_full_page_load_mobile_pwa_shell():
    """GET / renders minimal top bar, bottom dock, settings drawer, and zero-scroll Month view."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" in resp.text
    assert "KNPC Schedule" in resp.text
    assert "Year Grid" not in resp.text
    assert "Next Off" in resp.text
    assert "Full Wknd" in resp.text
    assert 'name="cal_month"' in resp.text
    assert 'name="cal_year"' in resp.text
    assert 'id="bottom-dock"' in resp.text
    assert 'id="settings-drawer"' in resp.text
    assert resp.headers.get("vary") == "HX-Request, Cookie"
    assert resp.headers.get("cache-control") == "private, no-cache"


def test_save_preference_cookie_and_shared_override():
    """save=1 writes knpc_pref cookie; shared links view without overwriting saved prefs."""
    save_client = TestClient(app)
    resp = save_client.get(
        "/?company=KOC&group=B&range=3months&view=weekends&save=1",
        headers={"HX-Request": "true"},
    )
    assert resp.status_code == 200
    assert "<!DOCTYPE html>" not in resp.text
    assert "Long Weekends" in resp.text
    assert save_client.cookies.get("knpc_pref") == "KOC:B:3months"
    assert "save=" not in resp.headers.get("hx-push-url", "")
    assert 'id="header-identity" hx-swap-oob="innerHTML"' in resp.text
    assert 'id="settings-drawer-body" hx-swap-oob="innerHTML"' in resp.text

    # Bare / launch restores saved KOC:B:3months from cookie
    resp_restored = save_client.get("/")
    assert resp_restored.status_code == 200
    assert "KOC &middot; Group B" in resp_restored.text

    # Visiting a shared link without save=1 shows override bar and keeps saved cookie
    resp_shared = save_client.get("/?company=KNPC&group=D")
    assert resp_shared.status_code == 200
    assert "Viewing shared <strong>KNPC Group D</strong>" in resp_shared.text
    assert "My KOC B" in resp_shared.text
    assert "Save as mine" in resp_shared.text
    assert save_client.cookies.get("knpc_pref") == "KOC:B:3months"


def test_htmx_view_panel_all_views_and_month_year_navigation():
    """HX-Target=view-panel renders all views and arbitrary month/year calendar picks."""
    for view in ("calendar", "weekends", "holidays", "schedule"):
        resp = client.get(
            f"/?company=KNPC&group=A&view={view}",
            headers={"HX-Request": "true", "HX-Target": "view-panel"},
        )
        assert resp.status_code == 200
        assert "<!DOCTYPE html>" not in resp.text
        assert 'id="bottom-dock" hx-swap-oob="innerHTML"' in resp.text
        assert 'id="desktop-tabs" hx-swap-oob="innerHTML"' in resp.text
        assert 'id="settings-form-state" hx-swap-oob="innerHTML"' in resp.text

    resp_feb_2028 = client.get(
        "/?company=KNPC&group=A&view=calendar&cal_year=2028&cal_month=2",
        headers={"HX-Request": "true", "HX-Target": "view-panel"},
    )
    assert resp_feb_2028.status_code == 200
    assert "<!DOCTYPE html>" not in resp_feb_2028.text
    assert '<option value="2" selected>February</option>' in resp_feb_2028.text
    assert '<option value="2028" selected>2028</option>' in resp_feb_2028.text
    assert "/day/2028-02-29" in resp_feb_2028.text


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


def test_exports_health_pwa_and_static_assets():
    """CSV, timed ICS, /health, /sw.js, manifest, and static assets return expected responses."""
    csv_resp = client.get("/export/csv?company=KOC&group=D&range=week")
    assert csv_resp.status_code == 200
    assert csv_resp.headers["content-type"].startswith("text/csv")
    assert 'filename="KOC_D_schedule.csv"' in csv_resp.headers["content-disposition"]
    assert "Date,Day of Week,Shift,Holiday" in csv_resp.text

    ics_resp = client.get("/export/ics?company=KNPC&group=A&range=month")
    assert ics_resp.status_code == 200
    assert ics_resp.headers["content-type"].startswith("text/calendar")
    assert "BEGIN:VCALENDAR" in ics_resp.text
    assert "TZID:Asia/Kuwait" in ics_resp.text
    assert "DTSTART;TZID=Asia/Kuwait:" in ics_resp.text

    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json() == {"status": "ok"}

    sw_resp = client.get("/sw.js")
    assert sw_resp.status_code == 200
    assert "javascript" in sw_resp.headers["content-type"]
    assert sw_resp.headers.get("cache-control") == "no-cache"
    assert sw_resp.headers.get("service-worker-allowed") == "/"

    manifest_resp = client.get("/static/manifest.webmanifest")
    assert manifest_resp.status_code == 200
    manifest = manifest_resp.json()
    assert manifest["display"] == "standalone"
    assert any(icon["sizes"] == "192x192" for icon in manifest["icons"])
    assert any(icon["sizes"] == "512x512" for icon in manifest["icons"])

    for asset in (
        "/static/css/app.css",
        "/static/js/htmx.min.js",
        "/static/img/logo.png",
        "/static/img/favicon.png",
        "/static/img/icon-192.png",
        "/static/img/icon-512.png",
    ):
        asset_resp = client.get(asset)
        assert asset_resp.status_code == 200, f"Failed asset: {asset}"
