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

On Windows, prefer `py -3` when `python` is unavailable. Before creating a recurring job, run `check` once and require a successful Bark test.

## Workflow

1. Translate the user's request into `--model`, `--capacity`, `--color`, and either `--city` or `--scope china`.
2. If Bark is not configured, ask only for the user's full Bark URL or key, then run `configure --bark-url ... --test`. Never echo or commit the secret.
3. Run `check` once. Report the exact Apple part numbers and stores found. Treat `unknown` or command failure as an error, never as out of stock.
4. When the user explicitly asks to start monitoring, run `schedule create` with the same filters. Update the named job instead of creating a duplicate.
5. Use `status` to verify the last successful check and task heartbeat.

## Examples

```text
python scripts/apple_stock_monitor.py configure --bark-url "https://api.day.app/KEY" --test
python scripts/apple_stock_monitor.py check --city 北京 --model "iPhone 18 Pro Max" --capacity "256 GB" --color 银色
python scripts/apple_stock_monitor.py schedule create --name beijing-18-pro-max --every 1 --city 北京 --model "iPhone 18 Pro Max" --capacity "256 GB" --color 银色
python scripts/apple_stock_monitor.py check --scope china --model "iPhone 18 Pro Max"
python scripts/apple_stock_monitor.py status
```

Use at least a three-minute interval for `--scope china`; one minute is acceptable for one city and a small SKU set. The script adds jitter and sends Bark only on state transitions.

## Failure handling

The script distinguishes `available`, `unavailable`, `ineligible`, and `unknown`. It sends a deduplicated Bark alert after repeated query failures and a recovery alert after service returns. The recurring installer creates an independent watchdog because a crashed checker cannot report its own death.

For Apple endpoint changes, product-code changes, missing stores, HTTP 541, schema errors, or repair work, read [references/maintenance.md](references/maintenance.md). For scheduler behavior and host limitations, read [references/scheduling.md](references/scheduling.md).
