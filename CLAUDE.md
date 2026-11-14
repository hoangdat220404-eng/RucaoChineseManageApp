# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A desktop app (pywebview) for managing a Chinese-language tutoring center ("Rucao"): tracking teachers, classes, students, attendance (via Teams call logs), Google Calendar sessions, and tuition billing. There is no build step — the frontend is plain HTML/CSS/JS served by a Flask backend, and `pywebview` wraps it in a native window.

- Language in code, comments, UI text, and commit messages is Vietnamese. Keep new code consistent with that (variable/field names in the data model are Vietnamese: `buoiDaHoc`, `buoiNghi`, `buoibatthuong`, `ngayBatDau`, etc.) — do not rename existing JSON keys to English.
- No test suite, linter, or build/bundle config exists in this repo.

## Running the app

```
pip install -r requirements.txt
python backend/main_app.py
```

This starts a Flask server (`backend/flask_server.py`) on `127.0.0.1:5000` in a background thread and opens a `pywebview` window pointed first at `backend/loading.html`, then redirects to the Flask root once background sync (Google Calendar scan + Teams token refresh) finishes.

To debug just the web UI in a normal browser instead of pywebview, run `python backend/flask_server.py`-equivalent manually (or just hit `http://127.0.0.1:5000/` after starting `main_app.py`) — `app.run(debug=False)` is hardcoded in `run_flask()`, so toggle `debug=True` there temporarily if you need Flask's debugger/reloader.

There are no automated tests. Verify changes by running the app and exercising the relevant page; check the terminal for the Vietnamese print-statement logs backend code relies on instead of a logger.

## Architecture

### Data flow: one JSON file is the database

`database/database.json` is the single source of truth, shaped as:

```
{ "<Teacher Name>": {
    "Age", "ID_Calendar", "Info",
    "Class": { "Rucao_<Initials>_<ClassName>": {
        "Members": { "<Student Name>": { "TuitionFee": {"K1": "Done"|"No_done", ...}, "Off_dates", "Study_dates", "isStudying" } },
        "Study_week_day": "Thứ 5, 10:00-11:30 | Chủ Nhật, 10:00-11:30",
        "TeamsConversationID", "ngayBatDau", "isActive": "True"|"False",
        "buoiDaHoc": { "<call GUID>": [date, start, end, durationStr, participants[], status] },
        "buoibatthuong": { "<call GUID>": [date, start, end, durationStr, participants[], isNormal, reasonCode] },
        "buoiNghi": { "YYYY-MM-DD": reasonText },
        "Notifications": [vangNghiCount, nghiCount, batThuongCount]
    } }
}}
```

Booleans are stored as the strings `"True"`/`"False"` in several places (not JSON booleans) — match existing convention when editing those fields. Flask endpoints read/write this whole file (no partial updates, no DB engine) — every write re-serializes the entire JSON, so concurrent writes are guarded with a bare `threading.Lock()` in `flask_server.py` (note: a new `Lock()` per request doesn't actually serialize anything across requests — be aware of this if touching concurrency-sensitive endpoints).

The frontend never talks to the filesystem directly; it calls the Flask JSON API (`/api/...`), caches the result in `sessionStorage` (`teacherClassDB`, `BillData`), and only explicitly refetches on forced refresh. `script/global.js` is loaded on every page and owns this cache plus the `pywebviewready` bootstrap and the notification badge on the home page.

### Backend (`backend/`)

- `main_app.py` — pywebview entrypoint. Runs Flask in a daemon thread, shows `loading.html` while `calendar_scanner.main()` (Google Calendar sync) and `Team_fetch.main()` (Teams token refresh + attendance processing) run, then redirects the window to the Flask app. Also owns the "save on window close" flow: on close it calls the frontend's `exportDataForSave()` JS function to pull `teacherClassData` back out of the page and writes it to `database.json` — meaning in-memory frontend edits are the real pending state until the window is closed.
- `flask_server.py` — all HTTP API routes (`/api/get-database`, `/api/add-teacher`, `/api/add-class`, `/api/update-class-status`, `/api/update-tuition-status`, `/api/update-class-abnormal-status`, `/api/update-all`, bill endpoints) plus serving the static frontend (`static_folder` points at the repo root). Also contains `process_bill_data()`, which derives "ready to bill" student/course entries from `calendar_scanner/data/bill.json` by looking for the last session (B8 or B12) of a course.
- `calendar_scanner/calendar_scanner.py` — all Google Calendar integration: OAuth (`token.json`/`credentials.json`, gitignored), scanning events to build `bill.json`, creating recurring class events (`create_calendar_events_for_class`, RRULE-based), deleting/truncating recurring events when a class is deactivated, and conflict-checking new class schedules against existing ones (`parse_schedule_string` / `check_schedule_overlap`). Session/bill naming convention parsed from calendar event titles: `B<session>K<course>` or `K<course>B<session>` followed by the student name (see `parse_session_event_title`).
- `teams_api/Team_fetch.py` — Microsoft Teams integration via Selenium (grabs a `skypetoken` by sniffing network requests with `selenium-wire`) then hits Teams' internal chat API directly to pull call history per class's `TeamsConversationID`. `process_class_messages()` reconciles call events against each class's weekly schedule to classify each session as Normal/Late/Absence/EndSoon or an "abnormal" (unscheduled/wrong-time) call, and infers missed days (`buoiNghi`) for days that should have had a class but didn't, with a 30-minute grace period after the scheduled end time before marking a day as missed.

Both `calendar_scanner` and `teams_api` write directly to `database/database.json` using paths relative to their own file location (`../../database/database.json`), independent of the Flask routes — keep that path consistent if the file ever moves.

### Frontend (`page/`, `script/`, `css/`)

Three pages, each a standalone HTML file with its own script, all sharing `global.js`:
- `index.html` — dashboard/launcher cards.
- `page/ClassAdd.html` + `script/Class_add.js` — add teachers/classes, schedule conflict UI.
- `page/classmanage.html` + `script/Classmange.js` (largest file, ~1500 lines) — the main class/attendance/tuition management UI: rendering per-class session history, toggling class active status, marking tuition paid, flagging abnormal sessions.
- `page/BillCal.html` + `script/Logic_bill_cal.js` + `script/imageDataBill.js` — picks a student/course that just finished and renders a billing summary image for the course.

No framework/bundler — plain DOM manipulation, `fetch()` to the `/api/*` endpoints, and `sessionStorage` as the client-side cache. When adding a new page, follow the existing pattern: include `script/global.js`, dispatch/listen for the `databaseReady` custom event rather than assuming `teacherClassData` is populated synchronously.

## Known gotchas

- `database/database.json` and `database/meeting_report.json` are gitignored, but `database/database.json` is already tracked in git from before the ignore rule was added (see `git status`) — edits to it will still show as a diff; don't assume ignoring means untracked.
- Secrets/credentials (`credentials.json`, `token.json`, `token.txt`, `.env`) are gitignored and expected to exist locally for Google/Teams auth — they are not in the repo.
- `backend/teams_api/Team_fetch.py` drives a real Chrome via Selenium with a persistent profile dir (`selenium_profile_for_teams/`) to capture a Teams auth token; it expects the user to be already logged into Teams in that Chrome profile.
