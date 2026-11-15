# AGENTS.md

Telegram bot that scans Firebase panels for Swiggy OTPs, auto-logs in, and harvests session
tokens into JSON stores. Single long-polling process, no CLI, no framework, no web server.

## Run / verify

```bash
pip3 install -r requirements.txt
python3 swiggy_bot.py          # or ./run_bot.sh (adds caffeinate on macOS)
./run_bot_forever.sh           # auto-restart loop; exits only on code 0
```

- **There are no tests, no linter, no CI, no formatter, no typecheck config.** Verify changes with
  `python3 -m py_compile swiggy_bot.py account_ops.py manual_login_cli.py`. There is no test suite to
  run; do not invent one.
- Requires Python 3.10+ (`str | None` unions used throughout; repo runs on 3.13).
- Bot token comes from `TELEGRAM_BOT_TOKEN` env, else `bot_token.txt`. Never hardcode it — and note
  `test_proxy.py` still has a live proxy credential inline; don't copy that pattern into new code.
- Only one instance can poll. A second one throws Telegram 409, which `main()` logs and swallows —
  a "bot not responding" report is usually a stale process still running.
- `main()` calls `bot.remove_webhook()` then `infinity_polling`. No webhook path exists.

## Layout

| Path | Role |
|---|---|
| `swiggy_bot.py` | Everything: config, HTTP, proxy pool, Firebase scan, OTP poll, Telegram UI (~4k lines) |
| `account_ops.py` | Standalone `Account` client for Swiggy REST + MCP APIs. Imports nothing from the bot |
| `manual_login_cli.py` | Standalone interactive OTP login, no imports from the bot |
| `SWIGGY_APIS.txt`, `swiggy_analysis*/` | Reverse-engineered endpoint dumps. Reference data, not code |
| `panels.txt`, `proxies.txt`, `firebase_disabled.txt` | Input lists, one per line, `#` comments allowed |
| `sessions.json`, `sessions_minimal.json`, `swiggy_store.json`, `swiggy_auto_log.json`, `individual_sessions/` | Runtime state — all gitignored, all present on disk |

`swiggy_bot.py` is laid out in `# ═══` banner sections (CONFIG, PROXY, STORE, SCAN, TELEGRAM UI,
PANELS, ACCOUNTS). Find code by function name, not by line; edit in place rather than refactoring
into modules.

## Session storage is triplicated — write all three

A harvested session lives in `sessions.json` (full), `sessions_minimal.json` (only
`mobile, token, sid, tid, deviceId, customerId`), and `individual_sessions/<mobile>.json`.
`save_session_record()` and `_persist_session_update()` both maintain all three. Any new field must
be threaded through `save_session_record`, `_persist_session_update`, and the minimal-key tuples in
`generate_sessions_zip()`, or the export silently drops it.

Dedupe is by `mobile` string — `already_saved()` short-circuits the whole login attempt, so a phone
number already in `sessions.json` will never be retried until its record is removed.

Use `_atomic_save(path, list)` for persisted JSON lists (writes `.tmp`, then `Path.replace`). Use
`_read_json_cached()` only for read-only tab rendering; it caches on `(mtime, size)`.

## Don't hand-edit state while the bot runs

`swiggy_store.json` is loaded once into the global `STORE` at boot and rewritten wholesale by
`save_store()`, so any edit made while the process is live is silently clobbered. The same applies to
`USED_NUMBERS`. Stop the bot before editing runtime JSON by hand.

`swiggy_auto_log.json` is append-by-full-rewrite (`append_log_entry` reads the entire list, appends,
rewrites). It is already megabytes. Do not add chatty per-request logging to it.

## Concurrency model

Threads everywhere: `infinity_polling` handler threads, a `run_worker` scan thread, a
`live_status_updater` thread, `_panel_autorefresh`, and ad-hoc `threading.Thread(..., daemon=True)`
per button. There is no async code.

- Module-level mutable globals (`STORE`, `USED_NUMBERS`, `STATS`, `AUTO_RUNNING`, `_proxy_pool`,
  `DISABLED_PANELS`, `_states`, `_PANEL_STATE`, `_JSON_CACHE`) are each paired with a `*_lock`.
  Reuse the existing lock; a new shared structure gets its own lock.
- `AUTO_RUNNING` is a plain global checked in `_panel_start()` — not lock-protected, so treat "start
  scan" as best-effort idempotent rather than atomic.
- Any Swiggy request through `get_swiggy_session()` should be wrapped by the 403 machinery:
  `wait_if_blocked()` before, `record_403()` / `clear_403()` after. Skipping it means no rotation and
  a silent IP block.
- LLS proxies (host containing `resfix-in-nnid`) must pass through `init_lls_session()` before use —
  `get_swiggy_session()` and `_acct_account()` already do this. A new HTTP path that calls
  `current_proxy()` directly will get an unusable proxy.

## Telegram UI conventions

- Four handlers only: `@bot.message_handler(commands=["start","menu"])`, `commands=["panel",
  "dashboard"]`, a catch-all `func=lambda m: True` → `handle_message`, and a catch-all
  `callback_query_handler` → `handle_callback` (which dispatches inline buttons by `callback_data`
  prefix, plus `_handle_panel_callback` / `_handle_acct_callback`).
- Multi-step text dialogs are a per-user state machine: `set_state(uid, step=...)` /
  `pop_state(uid)` keyed by `user_id`, branched at the top of `handle_message`. A new prompt flow
  means a new `step` string plus its branch — there is no conversation framework.
- Most `send_message`/`edit_message_text` calls use `parse_mode="HTML"`; on those, any user- or
  API-supplied text must go through `_panel_esc()` (or the local escaping already in scope).
  Unescaped `<` from a phone number or product name breaks the whole message with a 400.
- `handle_callback` must `bot.answer_callback_query(call.id)` or Telegram leaves a spinner on the
  button.

## Duplicated helpers — change both copies

`generate_device_fingerprint`/`build_login_headers` in `swiggy_bot.py` mirror
`generate_fingerprint`/`build_headers` in `manual_login_cli.py`, including `ANDROID_DEVICES` and the
Swiggy header set. Fingerprint or header changes must be made in both files or the manual login tool
harvests sessions the bot's API client can't use.

## Conventions

- Config constants are block-commented at the top of each file (`WORKERS`, `OTP_TIMEOUT`, `POLL_MIN/
  MAX`, `SCAN_WORKERS`, `MAX_AGE_MINUTES`, `IP_BLOCK_*`). Tune there, not inline.
- `from __future__ import annotations` at the top of every module; keep it.
- Long functions are the norm (`process_swiggy_single`, `handle_message`, `handle_callback`). Match
  the surrounding style — early-return guards, `log_func` callbacks for progress, dict results with
  `ok`/`status`/`data` from the HTTP layer.
- `account_ops.Account` returns dicts shaped `{"ok": bool, "status": int, "data": {...}}`; the UI
  layer reads `.get("data")` and never raises on transport failure.
- `git log` is empty — the repo has no commits, everything is untracked. Don't assume history to
  diff against.
