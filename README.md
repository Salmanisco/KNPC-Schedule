# KNPC Schedule

Fast, zero-login shift schedule planner for **KNPC** and **KOC** groups (`A`, `B`, `C`, `D`) with official **Kuwaiti public holidays**, **Long Weekend (`Fri + Sat Off`)** finder, and one-click **CSV / `.ics` calendar export**.

## What Changed in v2

Revamped from Streamlit + Pandas/NumPy into an ultra-lightweight hypermedia web app:

- **Backend:** **FastAPI** + **Jinja2** (`4` runtime packages: `fastapi`, `uvicorn[standard]`, `jinja2`, `holidays`) — no database, no login, no auth, no pandas/numpy bloat.
- **UI Stack:** **HTMX 2.0** (self-hosted `~50 KB`) + **Tailwind CSS v4 + DaisyUI v5** compiled via the zero-Node standalone Tailwind CLI (`public/static/css/app.css`), native `<dialog>` day inspector, Heroicons SVG macros, and Winter/Night light & dark themes.
- **Calendar & UX:** Sunday-first (`Su..Sa`) multi-month **Year Grid**, **Month Focus**, and **Agenda List** views; Today / Next Off / Next Fri+Sat Off summary cards; instant company & group toggle remembered locally via cookie; and `.ics` export for Apple/Google/Outlook calendars.
- **Optimized Assets:** Resized legacy `4.77 MB` `logo.png` down to `< 100 KB` (`logo.png`, `favicon.png`, `apple-touch-icon.png`) served directly from `public/static/`.

---

## Local Development (`uv`)

Requires [uv](https://docs.astral.sh/uv/) (Python 3.12).

```bash
# 1. Install dependencies into .venv
uv sync

# 2. (Optional, whenever editing templates or CSS) Build minified Tailwind + DaisyUI CSS
./scripts/build-css.sh

# 3. Run local dev server
uv run uvicorn main:app --reload
```

Open `http://127.0.0.1:8000`.

### Run Tests & Linter

```bash
uv run ruff check .
uv run pytest -v
```

---

## Cheapest / Free Cloud Deployment

### Option 1 — Vercel Hobby (`$0/mo`, Recommended)

Vercel natively detects `FastAPI` + `pyproject.toml` + `uv.lock`, runs serverless Fluid compute functions for free (non-commercial personal/team use, no credit card required), and serves `public/static/*` straight from Vercel's global Edge CDN:

1. Push this repository to GitHub (`git push`).
2. Import the repository in [Vercel](https://vercel.com/new) (Hobby tier — `$0/mo`).
3. Keep defaults (Vercel detects `main.py`, `pyproject.toml`, `uv.lock`, and `public/static/`) and click **Deploy**.

### Option 2 — Render Free (`$0/mo` via Blueprint)

1. Push this repository to GitHub.
2. In Render, choose **New -> Blueprint** and select this repo (reads [`render.yaml`](./render.yaml)).
3. Note: Render's free tier spins down after 15 minutes of inactivity (~50s cold start).

### Option 3 — Docker / OrbStack (Mac Studio or Fly.io)

Build and run the multi-stage non-root `uv` container defined in [`Dockerfile`](./Dockerfile):

```bash
docker build -t knpc-schedule .
docker run --rm -p 8000:8000 knpc-schedule
```
