---
name: apple-stock-monitor
description: Monitor Apple Retail pickup inventory by region, city, store, model, capacity, and color; configure Bark alerts; and create, inspect, or remove recurring monitor jobs. Use when the user asks to watch Apple Store stock, receive arrival alerts, resolve current Apple part numbers, or diagnose a broken Apple inventory monitor. Do not use for automatic checkout, cart mutation, reservations, or purchases.
---

# Apple Stock Monitor

Use the bundled deterministic script for inventory work. The skill never adds an item to a cart or places an order.

## Entry point

Resolve this skill directory and run:

```text
python scripts/apple_stock_monitor.py <command> ...
```

On Windows, prefer `py -3` when `python` is unavailable. The script performs one check at a time; recurring execution belongs to the host Agent's native scheduler. Never create Windows Task Scheduler jobs, launchd entries, systemd timers, or crontab entries.

## Workflow

1. On every invocation, run `status` before any stock or scheduling action. If `configured` is false, proactively tell the user that Bark is not configured and ask only for their full Bark URL or key; do this even when the user requested only a one-time query. Never echo or commit the secret. The one-time query may continue while waiting for it, but do not create a recurring Agent task until `configure --bark-url ... --test` succeeds.
2. Translate the user's request into an exact `--model`, `--capacity`, `--color`, and either `--city` or `--scope china`. Do not silently broaden `iPhone 17` to `iPhone 17e`, Pro, Pro Max, Plus, Air, or another family.
3. Run `check` once. Report every matched Apple part number and store. For broad queries, a compact summary is acceptable only if the complete part-number mapping remains visible. Treat `unknown` or command failure as an error, never as out of stock.
4. Group multi-store results by store. When using a Markdown table, emit a valid header cell for each column and do not omit variants returned by the script.
5. When the user explicitly asks to start monitoring, create or update a recurring monitor with the host Agent's native scheduling/automation tool and enable its failed-run notifications. The saved prompt must invoke this skill, run the exact `check` command, avoid creating nested schedules, and stay quiet while no action is needed because Bark handles alerts. If the scheduler supports a second native task in the same context, a companion may run `watchdog`; otherwise rely on the scheduler's failed-run notification and do not create an operating-system workaround.
6. Use `status` for the script's last successful check and state. Inspect, update, pause, or remove the recurring task through the same Agent scheduling tool that created it.

## Examples

```text
python scripts/apple_stock_monitor.py configure --bark-url "https://api.day.app/KEY" --test
python scripts/apple_stock_monitor.py check --city 北京 --model "iPhone 18 Pro Max" --capacity "256 GB" --color 银色
python scripts/apple_stock_monitor.py check --scope china --model "iPhone 18 Pro Max"
python scripts/apple_stock_monitor.py status
```

Use at least a three-minute interval for `--scope china`; one minute is acceptable for one city and a small SKU set. For each store and part number, Bark sends an arrival alert when availability first becomes `available`, then sends at most one reminder every 30 minutes while it remains available. If it leaves `available` and later returns, alert immediately without waiting for the cooldown. Different monitor jobs must not reset each other's notification state.

## Failure handling

The script distinguishes `available`, `unavailable`, `ineligible`, and `unknown`. It sends a deduplicated Bark alert after repeated query failures and a recovery alert after service returns. Configure the Agent automation to report its own failed runs, because a script that never starts cannot send Bark.

For Apple endpoint changes, product-code changes, missing stores, HTTP 541, schema errors, or repair work, read [references/maintenance.md](references/maintenance.md). For scheduler behavior and host limitations, read [references/scheduling.md](references/scheduling.md).
