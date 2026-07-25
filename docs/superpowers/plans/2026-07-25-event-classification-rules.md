# Event Classification Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the fallback calendar classifier and checked-in 2026 update SQL for the seven confirmed misclassified events without changing the homepage filter or the user's already-updated SQLite database.

**Architecture:** Preserve the existing `classify_event_by_name()` interface and make its decision order specific-to-general: WTT series first, then flexible Olympic qualification matching, then age/cup-aware continental families. Lock behavior down with a table-driven regression test using authoritative recent-event examples.

**Tech Stack:** Python 3.11, `unittest`, SQLite source SQL

---

### Task 1: Add classification regression coverage

**Files:**
- Modify: `scripts/db/test_event_classification_overrides.py`
- Test: `scripts/db/test_event_classification_overrides.py`

- [ ] **Step 1: Add a table-driven failing test**

Add this method to `EventClassificationOverrideTests`:

```python
def test_calendar_name_classifier_handles_recent_event_families(self):
    cases = {
        "Europe Smash – Sweden 2026": ("WTT Grand Smash", "--"),
        "Saudi Smash 2024": ("WTT Grand Smash", "--"),
        "Europe Youth Smash – Sweden 2026": ("WTT Youth Grand Smash", "--"),
        "ITTF-Americas Central America Youth Championships Tegucigalpa 2026": (
            "Regional",
            "Youth Championships",
        ),
        "ITTF-Americas South American Championships Santiago 2026": (
            "Regional",
            "Senior Championships",
        ),
        "ITTF-Americas South American Youth Championships Chapeco 2026": (
            "Regional",
            "Youth Championships",
        ),
        "ITTF-Americas Youth Championships Guatemala City 2026": (
            "Continental",
            "Youth Championships",
        ),
        "ITTF-Oceania Youth Championships Ballarat 2026": (
            "Continental",
            "Youth Championships",
        ),
        "ITTF-Oceania Cup Christchurch 2026": ("Continental", "Senior Cup"),
        "ITTF-Africa Youth Cup Accra 2026": ("Continental", "Youth Cup"),
        "ETTU Europe Youth Top 10 Antibes 2026": ("Continental", "Youth Cup"),
        "European Olympic Singles Qualification Sarajevo 2024": (
            "Olympic Qualification",
            "--",
        ),
    }

    for name, expected in cases.items():
        with self.subTest(name=name):
            self.assertEqual(
                expected,
                IMPORT_EVENTS_CALENDAR.classify_event_by_name(name),
            )
```

- [ ] **Step 2: Run the new test and verify RED**

Run:

```bash
python -m unittest scripts.db.test_event_classification_overrides.EventClassificationOverrideTests.test_calendar_name_classifier_handles_recent_event_families -v
```

Expected: FAIL for Europe/Saudi Smash and the affected continental family cases.

### Task 2: Repair classifier precedence

**Files:**
- Modify: `scripts/db/import_events_calendar.py:266-415`
- Test: `scripts/db/test_event_classification_overrides.py`

- [ ] **Step 1: Generalize Smash and Olympic qualification detection**

Replace venue-specific adult Smash detection with:

```python
elif 'Youth Smash' in name:
    return 'WTT Youth Grand Smash', '--'
elif 'Smash' in name:
    return 'WTT Grand Smash', '--'
```

Before the general Olympic Games branch, classify flexible qualification names:

```python
elif re.search(r'Youth\\s+Olympic.*Qualif(?:ication|ier)', name, re.IGNORECASE):
    return 'Youth Olympic Games Qualification', '--'
elif re.search(r'Olympic.*Qualif(?:ication|ier)', name, re.IGNORECASE):
    return 'Olympic Qualification', '--'
```

- [ ] **Step 2: Make continental branches age/cup aware**

Apply these precedence rules within their relevant organizer branches:

```python
if 'Youth' in name and ('Cup' in name or 'Top 10' in name or 'Top-10' in name
                        or 'Top 16' in name or 'Top-16' in name):
    return 'Continental', 'Youth Cup'
if 'U21' in name:
    return 'Continental', 'U21 Championships'
if 'Youth' in name:
    return 'Continental', 'Youth Championships'
if 'Cup' in name or 'Top 10' in name or 'Top-10' in name or 'Top 16' in name or 'Top-16' in name:
    return 'Continental', 'Senior Cup'
```

For ITTF-Americas, evaluate these regional patterns before its continental
fallback:

```python
is_regional_youth = (
    'North American Youth' in name
    or 'Central American Youth' in name
    or 'Central America Youth' in name
    or 'South American Youth' in name
)
if is_regional_youth:
    return 'Regional', 'Youth Championships'
if 'North American' in name or 'South American' in name:
    return 'Regional', 'Senior Championships'
```

Keep `Central American & Caribbean Championships` continental, matching its
authoritative event classification.

- [ ] **Step 3: Run the focused test and verify GREEN**

Run the Task 1 command.

Expected: all subtests PASS.

- [ ] **Step 4: Run the full classification test module**

Run:

```bash
python -m unittest scripts.db.test_event_classification_overrides -v
```

Expected: all tests PASS.

### Task 3: Correct the checked-in 2026 SQL artifact

**Files:**
- Modify: `data/events_calendar/cn/events_calendar_2026_update.sql`

- [ ] **Step 1: Correct the seven affected calendar statements**

Set the statements to the following type/kind/category triples:

```text
3246 -> WTT Grand Smash / -- / WTT_GRAND_SMASH
3406 -> Regional / Youth Championships / REGIONAL_YOUTH_CHAMPS
3407 -> Regional / Senior Championships / REGIONAL_CHAMPS
3410 -> Continental / Youth Championships / YOUTH_CONTINENTAL_CHAMPS
3455 -> Continental / Youth Championships / YOUTH_CONTINENTAL_CHAMPS
3494 -> Continental / Youth Cup / YOUTH_CONTINENTAL_CUP
ETTU Europe Youth Top 10 Antibes 2026
     -> Continental / Youth Cup / YOUTH_CONTINENTAL_CUP
```

Do not execute this SQL against `data/db/ittf.db`; the user has already
corrected the local database manually.

- [ ] **Step 2: Verify the artifact text**

Run:

```bash
rg -n -A4 -B1 \
  '3246|3406|3407|3410|3455|3494|ETTU Europe Youth Top 10 Antibes' \
  data/events_calendar/cn/events_calendar_2026_update.sql
```

Expected: each target statement contains the intended type, kind, and category.

### Task 4: End-to-end verification

**Files:**
- Test: `scripts/db/test_event_classification_overrides.py`
- Verify only: `data/db/ittf.db`

- [ ] **Step 1: Verify the user-updated database categories**

Run a read-only SQLite query joining `events_calendar` to `event_categories`
for the seven targets and selecting `events.category_code` for 3246 and 3455.

Expected: all rows match the categories listed in Task 3.

- [ ] **Step 2: Verify homepage data now includes event 3246**

Run:

```bash
./node_modules/.bin/tsx -e "
import {getHomeCalendar} from './lib/server/home';
const result=getHomeCalendar(2026);
const target=result.events.find((event: any) => event.eventId===3246);
if (!target) process.exit(1);
console.log(target);
"
```

from `web/`.

Expected: exit code 0 and the returned event has category code
`WTT_GRAND_SMASH`.

- [ ] **Step 3: Run import dry-run**

Run:

```bash
python scripts/db/import_events_calendar.py --year 2026 --dry-run
```

Expected: exit code 0, no database mutation, and no reported import errors.

- [ ] **Step 4: Check the final diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only the classification test, classifier, and
2026 update SQL (plus this approved plan) are changed.
