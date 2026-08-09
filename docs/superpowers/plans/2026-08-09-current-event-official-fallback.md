# Current Event Official Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep current-event completed statuses current when WTT omits the static take-10 file or more than ten matches complete close together.

**Architecture:** Prefer the small take-10 payload and fall back to the existing paginated Official fetcher only when take-10 is unavailable or invalid. Separately run strict full-Official reconciliation hourly and at session-window end without invoking match-details; all imports remain monotonic upserts.

**Tech Stack:** Python 3.10+, `urllib.request`, dataclasses, SQLite, `unittest`, existing current-event runtime and cron generator.

---

## File map

- `scripts/runtime/scrape_wtt_live_matches.py`: structured CDN outcomes, Official source selection, merge precedence, degraded summary.
- `scripts/runtime/test_scrape_wtt_live_matches.py`: source-selection, merge, and summary tests.
- `scripts/runtime/generate_current_event_crontab.py`: internal reconciliation source and timing.
- `scripts/runtime/test_generate_current_event_crontab.py`: command mapping and timing tests.
- `docs/scripts_overview.md`: script-level behavior.
- `docs/event-data-update-workflow.md`: operational cron behavior.

### Task 1: Select take-10 or full-Official fallback

**Files:**
- Modify: `scripts/runtime/scrape_wtt_live_matches.py:1-110,254-315`
- Test: `scripts/runtime/test_scrape_wtt_live_matches.py`

- [ ] **Step 1: Write failing source-selection tests**

Add `from unittest.mock import patch` and this class:

```python
class RecentOfficialSelectionTests(unittest.TestCase):
    def test_valid_take_10_avoids_full_fallback(self):
        take_10 = live.JsonFetchResult("https://cdn.test/take10", True, [{"documentCode": "A"}], None)
        with patch.object(live, "fetch_cdn_json_result", return_value=take_10), \
             patch.object(live, "fetch_all_official_results") as full_fetch:
            result = live.fetch_recent_official(3246)
        self.assertEqual("take_10", result.selected_source)
        self.assertEqual(1, len(result.items))
        self.assertFalse(result.degraded)
        full_fetch.assert_not_called()

    def test_valid_empty_take_10_avoids_full_fallback(self):
        take_10 = live.JsonFetchResult("https://cdn.test/take10", True, [], None)
        with patch.object(live, "fetch_cdn_json_result", return_value=take_10), \
             patch.object(live, "fetch_all_official_results") as full_fetch:
            result = live.fetch_recent_official(3246)
        self.assertEqual("take_10", result.selected_source)
        self.assertEqual([], result.items)
        full_fetch.assert_not_called()

    def test_invalid_take_10_uses_full_fallback(self):
        take_10 = live.JsonFetchResult("https://cdn.test/take10", False, None, "invalid JSON")
        meta = {"url": "https://api.test/official", "ok": True, "count": 2, "pages": 1}
        items = [{"documentCode": "A"}, {"documentCode": "B"}]
        with patch.object(live, "fetch_cdn_json_result", return_value=take_10), \
             patch.object(live, "fetch_all_official_results", return_value=(meta, items)) as full_fetch:
            result = live.fetch_recent_official(3246)
        self.assertEqual("full_official_fallback", result.selected_source)
        self.assertEqual(items, result.items)
        self.assertFalse(result.degraded)
        full_fetch.assert_called_once_with(3246)

    def test_both_sources_failing_is_degraded(self):
        take_10 = live.JsonFetchResult("https://cdn.test/take10", False, None, "HTTP 404")
        meta = {"url": "https://api.test/official", "ok": False, "count": 0, "pages": 0}
        with patch.object(live, "fetch_cdn_json_result", return_value=take_10), \
             patch.object(live, "fetch_all_official_results", return_value=(meta, [])):
            result = live.fetch_recent_official(3246)
        self.assertIsNone(result.selected_source)
        self.assertEqual([], result.items)
        self.assertTrue(result.degraded)
```

- [ ] **Step 2: Run tests and confirm red**

Run:

```bash
.venv/bin/python -m unittest scripts.runtime.test_scrape_wtt_live_matches.RecentOfficialSelectionTests -v
```

Expected: FAIL because the result types and selector do not exist.

- [ ] **Step 3: Implement explicit fetch and selection results**

Import `dataclass` and `fetch_all_official_results`, then add:

```python
@dataclass(frozen=True)
class JsonFetchResult:
    url: str
    ok: bool
    payload: Any
    error: str | None


@dataclass(frozen=True)
class RecentOfficialResult:
    items: list[dict[str, Any]]
    selected_source: str | None
    sources: dict[str, dict[str, Any]]
    degraded: bool
```

Replace the ambiguous CDN fetch implementation with:

```python
def fetch_cdn_json_result(path: str, retries: int = 2) -> JsonFetchResult:
    url = f"{CDN_BASE}{path}"
    last_error: str | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=CDN_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 204:
                    return JsonFetchResult(url, False, None, "HTTP 204 no content")
                body = decode_response_body(resp, resp.read())
                if body.startswith(b"\xef\xbb\xbf"):
                    body = body[3:]
                try:
                    payload = json.loads(body.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    return JsonFetchResult(url, False, None, f"invalid JSON response: {exc}")
                return JsonFetchResult(url, True, payload, None)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(0.5 * attempt)
    return JsonFetchResult(url, False, None, last_error or "unknown fetch error")


def fetch_cdn_json(path: str, retries: int = 2) -> Any:
    result = fetch_cdn_json_result(path, retries=retries)
    return result.payload if result.ok else None
```

Replace `fetch_take_10_official` with:

```python
def fetch_recent_official(event_id: int) -> RecentOfficialResult:
    path = f"/websitestaticapifiles/{event_id}/{event_id}_take_10_official_results.json"
    take_10 = fetch_cdn_json_result(path)
    take_10_ok = take_10.ok and isinstance(take_10.payload, list)
    error = take_10.error
    if take_10.ok and not isinstance(take_10.payload, list):
        error = f"expected list, got {type(take_10.payload).__name__}"
    sources = {"take_10": {"url": take_10.url, "ok": take_10_ok,
                            "count": len(take_10.payload) if take_10_ok else 0,
                            "error": error}}
    if take_10_ok:
        return RecentOfficialResult(take_10.payload, "take_10", sources, False)

    meta, items = fetch_all_official_results(event_id)
    full_ok = bool(meta.get("ok"))
    sources["full_official_fallback"] = {
        "url": meta.get("url"), "ok": full_ok,
        "count": len(items) if full_ok else 0,
        "pages": meta.get("pages", 0),
        "error": None if full_ok else "failed to fetch full Official results",
    }
    return RecentOfficialResult(
        items if full_ok else [],
        "full_official_fallback" if full_ok else None,
        sources,
        not full_ok,
    )
```

- [ ] **Step 4: Run tests and confirm green**

Run Step 2 again. Expected: four tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/runtime/scrape_wtt_live_matches.py scripts/runtime/test_scrape_wtt_live_matches.py
git commit -m "fix(runtime): fall back when take-10 is unavailable"
```

### Task 2: Merge Official data safely and report degradation

**Files:**
- Modify: `scripts/runtime/scrape_wtt_live_matches.py:254-448`
- Test: `scripts/runtime/test_scrape_wtt_live_matches.py`

- [ ] **Step 1: Write failing merge and summary tests**

Add `import tempfile` and:

```python
class OfficialMergeAndSummaryTests(unittest.TestCase):
    def test_official_replaces_live_with_same_code(self):
        live_item = {"match_code": "M1", "source_status": "LIVE", "score": "2-1"}
        official = {"match_code": "M1", "source_status": "OFFICIAL", "score": "3-1"}
        merged = live.merge_normalized_matches([live_item], [official])
        self.assertEqual([official], merged)

    def test_distinct_items_are_retained(self):
        merged = live.merge_normalized_matches(
            [{"match_code": "LIVE", "source_status": "LIVE"}],
            [{"match_code": "DONE", "source_status": "OFFICIAL"}],
        )
        self.assertEqual({"LIVE", "DONE"}, {item["match_code"] for item in merged})

    def test_degraded_official_is_warning_not_terminal_error(self):
        official = live.RecentOfficialResult([], None, {"take_10": {"ok": False}}, True)
        with tempfile.TemporaryDirectory() as tmp:
            summary = live.write_outputs(
                Path(tmp), 3246,
                [{"match_code": "LIVE", "source_status": "LIVE"}],
                official_result=official,
                schedule_cache_used=False,
                with_debug_files=False,
            )
        self.assertEqual([], summary["errors"])
        self.assertTrue(summary["degraded"])
        self.assertEqual(1, len(summary["warnings"]))
```

- [ ] **Step 2: Run tests and confirm red**

```bash
.venv/bin/python -m unittest scripts.runtime.test_scrape_wtt_live_matches.OfficialMergeAndSummaryTests -v
```

Expected: FAIL because merge and summary support do not exist.

- [ ] **Step 3: Implement Official precedence and summary metadata**

Add:

```python
def merge_normalized_matches(live_matches, official_matches):
    merged = {item["match_code"]: item for item in live_matches if item.get("match_code")}
    for item in official_matches:
        if item.get("match_code"):
            merged[item["match_code"]] = item
    return sorted(merged.values(), key=lambda item: (
        item.get("source_status") or "", item.get("table_no") or "", item.get("match_code") or ""
    ))
```

Refactor `scrape_event_matches` to return `(matches, official_result)`. Normalize all selected Official items with the existing take-10 structure logic, then call `merge_normalized_matches`. When `include_official` is false, use `RecentOfficialResult([], None, {}, False)`.

Extend `write_outputs(..., official_result: RecentOfficialResult, ...)` with:

```python
"warnings": (["official result supplement unavailable; live data retained"]
             if official_result.degraded else []),
"degraded": official_result.degraded,
"selected_official_source": official_result.selected_source,
"official_sources": official_result.sources,
```

Update `main()` to unpack the tuple and pass `official_result`. Keep return-code behavior based only on `summary["errors"]`, so optional Official failure never blocks valid live import.

- [ ] **Step 4: Run all live scraper tests**

```bash
.venv/bin/python -m unittest scripts.runtime.test_scrape_wtt_live_matches -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/runtime/scrape_wtt_live_matches.py scripts/runtime/test_scrape_wtt_live_matches.py
git commit -m "feat(runtime): report official fallback coverage"
```

### Task 3: Schedule strict hourly Official reconciliation

**Files:**
- Modify: `scripts/runtime/generate_current_event_crontab.py:20-45,289-360,400-440,500-575`
- Test: `scripts/runtime/test_generate_current_event_crontab.py`

- [ ] **Step 1: Write failing command and timing tests**

Add methods to `GenerateCurrentEventCrontabTests`:

```python
def test_official_reconcile_maps_only_to_completed(self):
    args = argparse.Namespace(
        python_bin="/venv/bin/python", project_root="/srv/ittf",
        live_event_data_root="data/live_event_data", emit_db_path=None,
        db_path=Path("data/db/ittf.db"), runtime_python_dir="scripts/runtime",
        event_id=3246, headless=True, use_cdp=False, cdp_port=9223, log_dir=None,
    )
    command = cron.build_refresh_command(args, {"official_reconcile"})
    self.assertIn("--sources completed", command)
    self.assertNotIn("match_details", command)
    self.assertNotIn("--include-official", command)

def test_session_adds_hourly_and_final_reconciliation(self):
    event = cron.Event(3246, "Europe Smash", "Europe/Stockholm")
    schedule = [cron.SessionDay(
        local_date=cron.date(2026, 8, 9), morning_session_start="10:00",
        afternoon_session_start=None, raw_sub_events_text="Main Draw",
        parsed_rounds_json='[{"stage_code":"MAIN_DRAW","round_code":"R32"}]',
    )]
    _, jobs = cron.build_jobs(event, schedule, "Europe/Stockholm")
    times = [job.run_at.strftime("%H:%M") for job in jobs
             if "official_reconcile" in job.sources]
    self.assertEqual(["10:05", "11:05", "12:05", "13:05", "14:05", "15:00"], times)
```

- [ ] **Step 2: Run focused tests and confirm red**

```bash
.venv/bin/python -m unittest \
  scripts.runtime.test_generate_current_event_crontab.GenerateCurrentEventCrontabTests.test_official_reconcile_maps_only_to_completed \
  scripts.runtime.test_generate_current_event_crontab.GenerateCurrentEventCrontabTests.test_session_adds_hourly_and_final_reconciliation -v
```

Expected: FAIL because the internal source is not mapped or scheduled.

- [ ] **Step 3: Add source mapping and pure timing helper**

Add to `SCRAPE_IMPORT_SOURCES`:

```python
"official_reconcile": ("completed", "completed"),
```

Place `official_reconcile` after `live` in `SOURCE_ORDER`. Add:

```python
def session_official_reconcile_times(session_start: datetime) -> list[datetime]:
    start = session_start.replace(second=0, microsecond=0)
    end = start + SESSION_REFRESH_DURATION
    points = []
    run_at = start + timedelta(minutes=5)
    while run_at < end:
        points.append(run_at)
        run_at += timedelta(hours=1)
    points.append(end)
    return points
```

In the per-session loop in `build_jobs`, after creating live range jobs:

```python
for reconcile_at in session_official_reconcile_times(session_start):
    add_job(jobs, reconcile_at, "official_reconcile", f"{session_label}-official-reconcile")
```

- [ ] **Step 4: Run all cron tests**

```bash
.venv/bin/python -m unittest scripts.runtime.test_generate_current_event_crontab -v
```

Expected: all tests PASS, including existing live and match-details mappings.

- [ ] **Step 5: Generate a 3246 dry-run crontab**

```bash
.venv/bin/python scripts/runtime/generate_current_event_crontab.py \
  --event-id 3246 --db-path data/db/ittf.db --include-past \
  --project-root /home/flyingfox/doubao_tt \
  --python-bin /home/flyingfox/.pyenv/versions/venv/bin/python \
  --live-event-data-root /home/flyingfox/doubao_tt/data/live_event_data \
  --emit-db-path /home/flyingfox/doubao_tt/data/db/ittf.db \
  --log-dir /home/flyingfox/doubao_tt/data/logs
```

Expected: live remains every ten minutes; reconciliation uses only `--sources completed`, contains no `match_details`, runs at the five-minute offset hourly, and runs once at session start plus five hours.

- [ ] **Step 6: Commit**

```bash
git add scripts/runtime/generate_current_event_crontab.py scripts/runtime/test_generate_current_event_crontab.py
git commit -m "feat(cron): reconcile official results hourly"
```

### Task 4: Document and verify end-to-end behavior

**Files:**
- Modify: `docs/scripts_overview.md:360-390`
- Modify: `docs/event-data-update-workflow.md:350-380`

- [ ] **Step 1: Document live fallback and reconciliation**

Add to `docs/scripts_overview.md`:

```markdown
- `live --include-official`优先读取 take-10；资源缺失、非 JSON 或结构异常时回退到分页 `GetOfficialResult`。两个 Official 来源都失败时仍导入有效 live 数据，并在 summary 标记 degraded。
- 内部 `official_reconcile` source 每小时及 session 五小时窗口结束时运行完整 Official 抓取/导入，不运行 `match_details`。
```

Add to `docs/event-data-update-workflow.md`:

```markdown
- **session 刷新窗口**：live 每 10 分钟运行，take-10 不可用时由完整 Official API 兜底。
- **Official 校准**：窗口内每小时及窗口结束时运行；只 upsert 返回结果，不删除或降级一次响应中缺失的比赛。
```

- [ ] **Step 2: Run the focused runtime suite**

```bash
.venv/bin/python -m unittest \
  scripts.runtime.test_scrape_wtt_live_matches \
  scripts.runtime.test_wtt_scrape_shared \
  scripts.runtime.test_import_current_event_live \
  scripts.runtime.test_import_current_event_official_results \
  scripts.runtime.test_generate_current_event_crontab \
  scripts.runtime.test_scrape_current_event \
  scripts.runtime.test_import_current_event -v
```

Expected: all tests PASS.

- [ ] **Step 3: Compile runtime scripts**

```bash
.venv/bin/python -m compileall -q scripts/runtime
```

Expected: exit 0 with no output.

- [ ] **Step 4: Inspect final changes**

```bash
git diff --check
git status --short
git diff --stat
```

Expected: only planned runtime implementation/tests and two docs are changed; nothing under `data/live_event_data`, `data/db`, or `data/logs` is modified.

- [ ] **Step 5: Commit docs**

```bash
git add docs/scripts_overview.md docs/event-data-update-workflow.md
git commit -m "docs(runtime): explain official reconciliation"
```

## Separate production authorization

Do not deploy or repair production data in this plan. After local verification, request separate confirmation before publishing runtime files, reinstalling managed crontabs, or running a one-off 3246 `completed` scrape/import.
