# ITTF Scraper v2 Runbook

## 1) Install dependencies
```bash
pip install playwright
playwright install chromium
```

## 2) Initialize session (manual login)
```bash
python ittf_matches_playwright_v2.py --init-session
```

When browser opens:
- Login manually
- Complete MFA/captcha manually if required
- Return to terminal and press ENTER

This saves session state to `data/session/ittf_storage_state.json`.

## 3) Run full scrape (2024-2026)
```bash
python ittf_matches_playwright_v2.py
```

## 4) Useful options
- `--years 2024,2025,2026`
- `--top-n 50`
- `--force` (ignore checkpoint done marks)
- `--stop-on-error`
- `--min-delay 5 --max-delay 18`
- `--min-player-gap 20 --max-player-gap 45`

## 5) Output
- Structured player files: `data/matches_complete_v2/*.json`
- Raw event captures: `data/raw_event_payloads/<player>/*.json`
- Resume checkpoint: `data/checkpoints/ittf_checkpoint_v2.json`

## 6) Risk-control behavior
If captcha/block/risk page is detected, script stops immediately to protect session/account.
