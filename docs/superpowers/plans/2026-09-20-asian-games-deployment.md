# Asian Games 2026 Deployment Plan

> **For agentic workers:** This plan is implemented locally; production execution requires an explicit `--apply` invocation by the maintainer.

**Goal:** Publish the changed web image and provide a repeatable, isolated deployment path for the 2026 Asian Games scraper, schedule data, event row, imports, and cron jobs.

**Architecture:** The Asian Games flow stays outside the WTT current-event updater. A guarded shell entry point stages only the Asian Games scripts/data, backs up SQLite before writes, creates event 6666 without relying on `events_calendar`, imports the session schedule and normalized snapshot, verifies counts/timezone, and optionally replaces only the marked Asian Games crontab block.

**Tech Stack:** Bash, SSH/SCP, SQLite, Python 3.11, Docker Desktop/WSL2, Alibaba Cloud ACR.

---

## Files and boundaries

- `deploy/server/update_asian_games_2026.sh`: local deployment entry point. It prints a plan by default and requires `--apply` for SSH/SCP or production writes.
- `scripts/asian_games_2026/install_crontab.sh`: Asian Games-only cron installer; accepts `PYTHON_BIN` so the server does not need a project-local `.venv`.
- `scripts/asian_games_2026/`: one-off scraper, normalizer, importer, finalizer, and cron code. It is never merged into the WTT scraper flow.
- `data/asian_games/2026/`: raw/normalized Asian Games snapshots and logs/state.
- `data/event_schedule/6666.json`: human/session schedule imported into `current_event_session_schedule`.

## Step 1: Repair Docker Desktop WSL integration locally

The current error is from Docker Desktop's WSL shim: `/usr/bin/docker` points to a Docker Desktop CLI path that is unavailable until the Ubuntu distribution is integrated.

In Docker Desktop on Windows:

1. Start Docker Desktop.
2. Open **Settings → Resources → WSL Integration**.
3. Enable integration for **Ubuntu** and choose **Apply & Restart**.
4. Open a new WSL shell and run:

```bash
hash -r
docker version
docker info
```

Both commands must return client/server information before building. If WSL integration cannot be enabled, run the existing Windows batch script from a Docker-enabled PowerShell/CMD checkout:

```powershell
deploy\web\build-and-push.bat v1.1.2
```

## Step 2: Publish the web image

From the repository root, ensure `deploy/web/.env` exists and contains the required public IDs and Sentry settings. Do not put `SENTRY_AUTH_TOKEN` in a `--build-arg`; the script uses a BuildKit secret.

```bash
docker login crpi-0nufvytst96nosej.cn-beijing.personal.cr.aliyuncs.com
./deploy/web/build-and-push.sh v1.1.2
```

The script pushes both `:v1.1.2` and `:latest`. Updating the server's `ITTF_WEB_IMAGE` and restarting Docker Compose is a separate, manually authorized production step.

## Step 3: Review the Asian Games deployment plan

The default mode is read-only and does not invoke SSH or SCP:

```bash
./deploy/server/update_asian_games_2026.sh
```

The plan stages only:

```text
scripts/asian_games_2026/
data/asian_games/2026/
data/event_schedule/6666.json
```

It does not upload the full repository, replace WTT scripts, or overwrite unrelated crontab entries.

## Step 4: Execute the Asian Games deployment manually

After reviewing the printed plan and confirming the target host, run:

```bash
./deploy/server/update_asian_games_2026.sh --apply
```

The guarded script performs these operations in order:

1. Check the configured remote Python (default `/home/flyingfox/.pyenv/shims/python3.11`).
2. Upload and extract the isolated Asian Games bundle.
3. Back up `data/db/ittf.db` as `data/db/backups/ittf-before-asian-games-2026-*.db` and retain the newest five backups by default.
4. Upsert event 6666 with category 6, dates `2026-09-20` through `2026-09-28`, `JPN`, `in_progress`, and `Asia/Tokyo`; this does not require a remote `events_calendar` row.
5. Import `data/event_schedule/6666.json` through the existing session-schedule importer.
6. Import `data/asian_games/2026/normalized/current_matches.json` through `scripts.asian_games_2026.import_current`.
7. Verify the event row, valid timezone, schedule rows, team ties, matches, team roster players, and match players.
8. Install the marked Asian Games cron block using `PYTHON_BIN`.

To publish data and scripts but defer cron installation:

```bash
./deploy/server/update_asian_games_2026.sh --apply --skip-cron
```

The production command is intentionally not run as part of local verification.

## Step 5: Read-only production checks after a manual deployment

Run these commands manually if the deployment owner wants an independent check:

```bash
ssh flyingfox@xiaodoubao.site \
  "cd doubao_tt && /home/flyingfox/.pyenv/shims/python3.11 - <<'PY'
import sqlite3
conn = sqlite3.connect('data/db/ittf.db')
print(conn.execute('SELECT event_id,name,lifecycle_status,time_zone FROM events WHERE event_id=6666').fetchone())
for table in ('current_event_session_schedule','current_event_team_ties','current_event_matches','current_event_team_tie_side_players','current_event_match_side_players'):
    print(table, conn.execute('SELECT COUNT(*) FROM '+table+' WHERE event_id=6666').fetchone()[0])
PY"
```

Check the installed block without editing anything:

```bash
ssh flyingfox@xiaodoubao.site 'crontab -l | sed -n "/BEGIN ITTF ASIAN GAMES 2026/,/END ITTF ASIAN GAMES 2026/p"'
```

## Step 6: Stop or roll back manually

- Stop future Asian Games refreshes by removing only the marked block with `crontab -e`.
- Before any database restore, stop application writes, identify the desired `ittf-before-asian-games-2026-*.db` backup, and make a second copy of the current database. Restore only after a maintainer confirms the exact backup path.
- Roll back the web image by changing `ITTF_WEB_IMAGE` to the previous immutable ACR tag, then running `docker compose ... pull web` and `docker compose ... up -d` on the server.

## Local verification

Run after the files are changed:

```bash
bash -n deploy/server/update_asian_games_2026.sh
bash -n scripts/asian_games_2026/install_crontab.sh
./deploy/server/update_asian_games_2026.sh | grep -F 'no remote commands will run without --apply'
python -m unittest discover -s scripts/asian_games_2026/tests -p 'test_*.py'
git diff --check
```

The plan-only invocation must exit without calling `ssh`, `scp`, Docker, or modifying any production state.
