#!/usr/bin/env python3
"""Apple Retail pickup monitor with Bark notifications and no third-party packages."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_URL = "https://www.apple.com.cn"
PICKUP_ENDPOINT = f"{BASE_URL}/shop/retail/pickup-message"
BUY_ROOT = f"{BASE_URL}/shop/buy-iphone"
DEFAULT_HOME = Path.home() / ".apple-stock-monitor"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152 Safari/537.36"
)
CITY_POSTCODES = {
    "北京": "100000", "上海": "200000", "天津": "300000", "重庆": "400000",
    "广州": "510000", "深圳": "518000", "成都": "610000", "杭州": "310000",
    "南京": "210000", "苏州": "215000", "无锡": "214000", "宁波": "315000",
    "武汉": "430000", "长沙": "410000", "西安": "710000", "郑州": "450000",
    "济南": "250000", "青岛": "266000", "沈阳": "110000", "大连": "116000",
    "厦门": "361000", "福州": "350000", "合肥": "230000", "昆明": "650000",
    "南宁": "530000"
}

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


class MonitorError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def monitor_home() -> Path:
    return Path(os.environ.get("APPLE_STOCK_MONITOR_HOME", DEFAULT_HOME)).expanduser()


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as exc:
        backup = path.with_suffix(path.suffix + f".broken-{int(time.time())}")
        try:
            path.replace(backup)
        except OSError:
            pass
        raise MonitorError(f"配置文件损坏，已尝试保留为 {backup}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def curl_request(url: str, payload: dict[str, Any] | None, timeout: int,
                 original_error: Exception | None = None) -> bytes:
    curl = shutil.which("curl")
    if not curl:
        raise MonitorError(f"系统没有 curl，原始网络错误: {original_error}") from original_error
    command = [
        curl, "-L", "--compressed", "--fail-with-body", "--silent", "--show-error",
        "--max-time", str(timeout), "-A", USER_AGENT,
        "-H", "Accept: application/json, text/javascript, */*; q=0.01",
        "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.7",
        "-H", "X-Requested-With: XMLHttpRequest"
    ]
    input_data = None
    if payload is not None:
        input_data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        command += ["-H", "Content-Type: application/json; charset=utf-8", "--data-binary", "@-"]
    command.append(url)
    completed = subprocess.run(command, input=input_data, capture_output=True, timeout=timeout + 5)
    if completed.returncode:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise MonitorError(f"curl 请求失败: {detail or original_error}") from original_error
    if len(completed.stdout) > 4 * 1024 * 1024:
        raise MonitorError("远端响应超过 4 MiB 安全上限")
    return completed.stdout


def request(url: str, *, params: dict[str, Any] | list[tuple[str, Any]] | None = None,
            payload: dict[str, Any] | None = None, timeout: int = 35) -> bytes:
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}{'&' if '?' in url else '?'}{query}"
    data = None
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        "X-Requested-With": "XMLHttpRequest"
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if platform.system() == "Windows" and shutil.which("curl"):
        return curl_request(url, payload, timeout)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=timeout) as response:
            body = response.read(4 * 1024 * 1024 + 1)
            if len(body) > 4 * 1024 * 1024:
                raise MonitorError("远端响应超过 4 MiB 安全上限")
            return body
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as first_error:
        if not shutil.which("curl"):
            if isinstance(first_error, urllib.error.HTTPError):
                raise MonitorError(f"HTTP {first_error.code}: {urllib.parse.urlsplit(url).path}") from first_error
            raise MonitorError(f"网络请求失败: {first_error}") from first_error
        return curl_request(url, payload, timeout, first_error)


def request_text(url: str) -> str:
    return request(url).decode("utf-8", errors="replace")


def request_json(url: str, *, params: dict[str, Any] | list[tuple[str, Any]] | None = None,
                 payload: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = request(url, params=params, payload=payload)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MonitorError("Apple 接口没有返回有效 JSON，接口可能已经变化") from exc
    if not isinstance(value, dict):
        raise MonitorError("Apple JSON 顶层结构异常")
    return value


def clean_html(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = re.sub(r"(?:脚注|Footnote)\s*\d+", "", html.unescape(text), flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def extract_object_after_key(page: str, key: str) -> dict[str, Any]:
    marker = page.find("PRODUCT_SELECTION_BOOTSTRAP")
    key_index = page.find(key, max(marker, 0))
    if key_index < 0:
        raise MonitorError(f"购买页中没有 {key}")
    start = page.find("{", page.find(":", key_index + len(key)))
    if start < 0:
        raise MonitorError(f"{key} 后没有 JSON 对象")
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(page)):
        character = page[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(page[start:index + 1])
                except json.JSONDecodeError as exc:
                    raise MonitorError(f"{key} JSON 无法解析") from exc
    raise MonitorError(f"{key} JSON 对象不完整")


def display_value(data: dict[str, Any], dimension: str, key: Any) -> str:
    entry = data.get("displayValues", {}).get(dimension, {}).get(str(key), {})
    return clean_html(entry.get("value") if isinstance(entry, dict) else key) or clean_html(key)


def family_title(product: dict[str, Any], family: str) -> str:
    raw = str(product.get("familyType") or family).lower().replace("-", "").replace("_", "")
    match = re.search(r"iphone(\d+)(pro)?(max)?", raw)
    if match:
        return f"iPhone {match.group(1)}{' Pro' if match.group(2) else ''}{' Max' if match.group(3) else ''}"
    words = {"iphone": "iPhone", "pro": "Pro", "max": "Max", "air": "Air", "mini": "mini"}
    return " ".join(words.get(word, word.title()) for word in family.split("-"))


def normalize_products(family: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for product in data.get("products", []):
        part_number = product.get("partNumber")
        if not part_number:
            continue
        dimensions = {
            key: display_value(data, key, value)
            for key, value in product.items() if key.startswith("dimension")
        }
        model = family_title(product, family)
        screen = dimensions.get("dimensionScreensize", "").replace(model, "").strip()
        title_parts = [model, screen, dimensions.get("dimensionCapacity"), dimensions.get("dimensionColor")]
        title = " · ".join(dict.fromkeys(part for part in title_parts if part))
        result.append({
            "partNumber": part_number,
            "family": family,
            "model": model,
            "capacity": dimensions.get("dimensionCapacity", ""),
            "color": dimensions.get("dimensionColor", ""),
            "title": title,
            "buyUrl": f"{BUY_ROOT}/{family}"
        })
    return result


def discover_families() -> list[str]:
    root = request_text(BUY_ROOT)
    found = re.findall(r"/shop/buy-iphone/([^\"?#/]+)", root)
    families = list(dict.fromkeys(item for item in found if item.startswith("iphone") and len(item) < 80))
    if not families:
        raise MonitorError("Apple iPhone 页面没有发现任何产品系列")
    return families


def refresh_catalog() -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    failures: list[str] = []
    for family in discover_families():
        try:
            data = extract_object_after_key(request_text(f"{BUY_ROOT}/{family}"), "productSelectionData")
            normalized = normalize_products(family, data)
            if not normalized:
                raise MonitorError("没有产品")
            products.extend(normalized)
        except MonitorError as exc:
            failures.append(f"{family}: {exc}")
        time.sleep(0.35)
    if not products:
        raise MonitorError("Apple 购买页全部解析失败: " + "; ".join(failures))
    unique = {product["partNumber"]: product for product in products}
    catalog = {"updatedAt": utc_now(), "products": list(unique.values()), "failures": failures}
    write_json(monitor_home() / "catalog.json", catalog)
    return catalog["products"]


def load_catalog(force: bool = False) -> list[dict[str, Any]]:
    path = monitor_home() / "catalog.json"
    if not force and path.exists() and time.time() - path.stat().st_mtime < 12 * 3600:
        cached = read_json(path, {})
        if cached.get("products"):
            return cached["products"]
    return refresh_catalog()


def compact(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.casefold())


def normalize_capacity(value: str) -> str:
    normalized = compact(value).upper()
    if normalized.endswith("G"):
        normalized += "B"
    if normalized.endswith("T"):
        normalized += "B"
    return normalized


def resolve_products(model: str, capacity: str | None, color: str | None,
                     refresh: bool = False) -> list[dict[str, Any]]:
    wanted_model = compact(model)
    wanted_capacity = normalize_capacity(capacity) if capacity else None
    wanted_color = compact(color) if color else None
    matches = []
    for product in load_catalog(force=refresh):
        product_model = compact(product.get("model", ""))
        if wanted_model not in product_model:
            continue
        if wanted_model.endswith("pro") and product_model.endswith("promax"):
            continue
        if wanted_capacity and normalize_capacity(product.get("capacity", "")) != wanted_capacity:
            continue
        if wanted_color and wanted_color not in compact(product.get("color", "")):
            continue
        matches.append(product)
    if not matches:
        raise MonitorError(f"没有找到匹配商品: {model} {capacity or ''} {color or ''}".strip())
    return matches


def pickup_stores(part_numbers: list[str], location: str) -> list[dict[str, Any]]:
    params: list[tuple[str, str]] = [(f"parts.{index}", part) for index, part in enumerate(part_numbers)]
    params.append(("location", location))
    payload = request_json(PICKUP_ENDPOINT, params=params)
    api_status = int(payload.get("head", {}).get("status", 200))
    body = payload.get("body", {})
    if api_status >= 400:
        raise MonitorError(f"Apple 业务状态异常: {api_status}")
    stores = body.get("stores")
    if not isinstance(stores, list):
        message = body.get("errorMessage") or "响应中没有门店列表"
        raise MonitorError(f"Apple 库存响应异常: {message}")
    return stores


def classify_part(info: dict[str, Any] | None) -> str:
    if not isinstance(info, dict):
        return "unknown"
    display = str(info.get("pickupDisplay", "")).lower()
    if display in {"available", "unavailable", "ineligible"}:
        return display
    buyability = info.get("buyability", {})
    if isinstance(buyability, dict) and buyability.get("status") in {"COMING_SOON", "NOT_FOR_SALE"}:
        return "unknown"
    return "unknown"


def parse_results(stores: list[dict[str, Any]], products: list[dict[str, Any]],
                  city: str | None) -> list[dict[str, Any]]:
    results = []
    for store in stores:
        store_city = clean_html(store.get("city"))
        if city and compact(city) not in compact(store_city):
            continue
        availability = store.get("partsAvailability", {})
        for product in products:
            part = product["partNumber"]
            info = availability.get(part)
            if not info:
                info = next((value for value in availability.values()
                             if isinstance(value, dict) and value.get("partNumber") == part), None)
            regular = info.get("messageTypes", {}).get("regular", {}) if isinstance(info, dict) else {}
            results.append({
                "storeNumber": store.get("storeNumber"),
                "storeName": store.get("storeName"),
                "city": store_city,
                "partNumber": part,
                "product": product["title"],
                "status": classify_part(info),
                "quote": regular.get("storePickupQuote") or (info or {}).get("pickupSearchQuote") or "",
                "buyUrl": product["buyUrl"]
            })
    return results


def load_config() -> dict[str, Any]:
    return read_json(monitor_home() / "config.json", {})


def bark_push(title: str, body: str, url: str | None = None, notification_id: str | None = None) -> None:
    bark_url = load_config().get("barkUrl") or os.environ.get("APPLE_STOCK_BARK_URL")
    if not bark_url:
        raise MonitorError("尚未配置 Bark URL")
    if not bark_url.startswith(("https://", "http://")):
        bark_url = f"https://api.day.app/{bark_url.strip('/')}"
    payload: dict[str, Any] = {"title": title, "body": body, "group": "Apple库存", "level": "timeSensitive"}
    if url:
        payload["url"] = url
    if notification_id:
        payload["id"] = notification_id
    response = request_json(bark_url, payload=payload)
    if int(response.get("code", 200)) != 200:
        raise MonitorError(f"Bark 推送失败: {response.get('message') or response.get('code')}")


def save_config(bark_url: str, test: bool) -> None:
    if not bark_url.startswith(("https://", "http://")):
        bark_url = f"https://api.day.app/{bark_url.strip('/')}"
    parsed = urllib.parse.urlsplit(bark_url)
    if not parsed.netloc or len(parsed.path.strip("/")) < 4:
        raise MonitorError("Bark URL 或 Key 格式无效")
    config_path = monitor_home() / "config.json"
    write_json(config_path, {"barkUrl": bark_url, "updatedAt": utc_now()})
    if platform.system() != "Windows":
        config_path.chmod(0o600)
    if test:
        bark_push("Apple 库存监控", "Bark 配置成功，后续有货或任务异常会在这里提醒。")


def record_failure(message: str) -> None:
    path = monitor_home() / "state.json"
    state = read_json(path, {})
    state["lastAttempt"] = utc_now()
    state["lastError"] = message
    state["consecutiveFailures"] = int(state.get("consecutiveFailures", 0)) + 1
    now = time.time()
    last_push = float(state.get("lastErrorPushEpoch", 0))
    if state["consecutiveFailures"] >= 3 and now - last_push >= 1800:
        try:
            bark_push("Apple 库存监控异常", f"连续 {state['consecutiveFailures']} 次查询失败：{message}", notification_id="apple-stock-error")
            state["lastErrorPushEpoch"] = now
        except MonitorError as push_error:
            state["lastBarkError"] = str(push_error)
    write_json(path, state)


def record_success(results: list[dict[str, Any]]) -> None:
    path = monitor_home() / "state.json"
    state = read_json(path, {})
    was_failing = int(state.get("consecutiveFailures", 0)) >= 3
    statuses = {f"{item['storeNumber']}:{item['partNumber']}": item["status"] for item in results}
    notified = state.get("notifiedAvailable", {})
    newly_available = [item for item in results if item["status"] == "available" and not notified.get(f"{item['storeNumber']}:{item['partNumber']}")]
    current_available = {key for key, status in statuses.items() if status == "available"}
    notified = {key: value for key, value in notified.items() if key in current_available}
    state.update({
        "lastAttempt": utc_now(), "lastSuccess": utc_now(), "lastError": None,
        "consecutiveFailures": 0, "statuses": statuses, "resultCount": len(results),
        "notifiedAvailable": notified
    })
    write_json(path, state)
    if was_failing:
        try:
            bark_push("Apple 库存监控已恢复", f"库存接口恢复正常，本轮获得 {len(results)} 条结果。", notification_id="apple-stock-error")
        except MonitorError:
            pass
    for item in newly_available:
        body = f"{item['city']} · {item['storeName']}\n{item['product']}\n{item['quote'] or '现在可取货'}"
        key = f"{item['storeNumber']}:{item['partNumber']}"
        try:
            bark_push("Apple 到货提醒", body, item["buyUrl"], f"apple-stock-{item['storeNumber']}-{item['partNumber']}")
            state["notifiedAvailable"][key] = True
        except MonitorError as exc:
            state["lastBarkError"] = str(exc)
    write_json(path, state)


def record_warning(message: str) -> None:
    path = monitor_home() / "state.json"
    state = read_json(path, {})
    state["lastWarning"] = message
    state["consecutiveWarnings"] = int(state.get("consecutiveWarnings", 0)) + 1
    now = time.time()
    if state["consecutiveWarnings"] >= 3 and now - float(state.get("lastWarningPushEpoch", 0)) >= 1800:
        try:
            bark_push("Apple 库存监控部分异常", message, notification_id="apple-stock-warning")
            state["lastWarningPushEpoch"] = now
        except MonitorError as exc:
            state["lastBarkError"] = str(exc)
    write_json(path, state)


def clear_warning() -> None:
    path = monitor_home() / "state.json"
    state = read_json(path, {})
    if int(state.get("consecutiveWarnings", 0)) >= 3:
        try:
            bark_push("Apple 库存监控完整恢复", "所有区域和商品代码均已恢复正常。", notification_id="apple-stock-warning")
        except MonitorError:
            pass
    state["consecutiveWarnings"] = 0
    state["lastWarning"] = None
    write_json(path, state)


def locations_for(city: str | None, scope: str | None) -> list[tuple[str | None, str]]:
    if scope == "china":
        return [(name, postcode) for name, postcode in CITY_POSTCODES.items()]
    if not city:
        raise MonitorError("请使用 --city 城市名，或使用 --scope china")
    postcode = CITY_POSTCODES.get(city)
    if not postcode:
        raise MonitorError(f"尚无 {city} 的位置锚点，请在 CITY_POSTCODES 中补充")
    return [(city, postcode)]


def run_check(args: argparse.Namespace) -> list[dict[str, Any]]:
    products = resolve_products(args.model, args.capacity, args.color, args.refresh_catalog)
    part_numbers = [item["partNumber"] for item in products]
    all_stores: dict[str, dict[str, Any]] = {}
    errors = []
    for index, (city, location) in enumerate(locations_for(args.city, args.scope)):
        try:
            for store in pickup_stores(part_numbers, location):
                if store.get("storeNumber"):
                    all_stores[store["storeNumber"]] = store
        except MonitorError as exc:
            errors.append(f"{city or location}: {exc}")
        if index + 1 < len(locations_for(args.city, args.scope)):
            time.sleep(0.4)
    if not all_stores:
        raise MonitorError("所有库存查询均失败: " + "; ".join(errors))
    results = parse_results(list(all_stores.values()), products, args.city)
    if not results:
        raise MonitorError(f"Apple 返回了门店，但没有匹配到 {args.city or '中国大陆'} 的监控结果")
    unknown_count = sum(item["status"] == "unknown" for item in results)
    if unknown_count == len(results):
        raise MonitorError("所有商品状态均为 unknown，商品代码或响应结构可能已经变化")
    record_success(results)
    warnings = list(errors)
    if unknown_count:
        warnings.append(f"{unknown_count} 条商品状态为 unknown，可能存在商品代码或响应结构变化")
    if warnings:
        record_warning("；".join(warnings))
    else:
        clear_warning()
    output = {
        "checkedAt": utc_now(), "products": products, "storeCount": len(all_stores),
        "results": results, "partialErrors": errors
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return results


def watchdog(max_age_minutes: int) -> None:
    state = read_json(monitor_home() / "state.json", {})
    timestamp = state.get("lastSuccess")
    if not timestamp:
        bark_push("Apple 库存任务未运行", "尚未发现成功查询记录，请检查定时任务。", notification_id="apple-stock-watchdog")
        return
    last_success = datetime.fromisoformat(timestamp).timestamp()
    age = time.time() - last_success
    if age > max_age_minutes * 60:
        bark_push("Apple 库存任务心跳超时", f"已经 {int(age // 60)} 分钟没有成功查询，请检查电脑、网络和定时任务。", notification_id="apple-stock-watchdog")


def task_slug(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-")
    return (safe or hashlib.sha256(name.encode()).hexdigest()[:12])[:48]


def check_cli_args(args: argparse.Namespace) -> list[str]:
    values = ["check", "--model", args.model]
    if args.city:
        values += ["--city", args.city]
    if args.scope:
        values += ["--scope", args.scope]
    if args.capacity:
        values += ["--capacity", args.capacity]
    if args.color:
        values += ["--color", args.color]
    return values


def install_schedule(args: argparse.Namespace) -> None:
    if args.scope == "china" and args.every < 3:
        raise MonitorError("全国监控间隔不得小于 3 分钟")
    if not (load_config().get("barkUrl") or os.environ.get("APPLE_STOCK_BARK_URL")):
        raise MonitorError("创建任务前必须先配置并测试 Bark")
    home = monitor_home()
    home.mkdir(parents=True, exist_ok=True)
    slug = task_slug(args.name)
    script = Path(__file__).resolve()
    check_command = [sys.executable, str(script), *check_cli_args(args)]
    watchdog_command = [sys.executable, str(script), "watchdog", "--max-age", str(max(5, args.every * 3))]
    if platform.system() == "Windows":
        check_wrapper = home / f"run-{slug}.cmd"
        watchdog_wrapper = home / f"watchdog-{slug}.cmd"
        check_wrapper.write_text("@echo off\r\nset PYTHONUTF8=1\r\n" + subprocess.list2cmdline(check_command) + " >> \"%~dp0monitor.log\" 2>&1\r\n", encoding="utf-8")
        watchdog_wrapper.write_text("@echo off\r\nset PYTHONUTF8=1\r\n" + subprocess.list2cmdline(watchdog_command) + " >> \"%~dp0watchdog.log\" 2>&1\r\n", encoding="utf-8")
        for task_name, every, wrapper in [
            (f"AppleStockMonitor-{slug}", args.every, check_wrapper),
            (f"AppleStockWatchdog-{slug}", max(5, args.every * 3), watchdog_wrapper)
        ]:
            command = ["schtasks", "/Create", "/TN", task_name, "/SC", "MINUTE", "/MO", str(every), "/TR", str(wrapper), "/F"]
            completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
            if completed.returncode:
                raise MonitorError(f"创建 Windows 任务失败: {completed.stderr or completed.stdout}")
    else:
        marker = f"apple-stock-monitor:{slug}"
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
        kept = [line for line in existing if marker not in line]
        schedule = "* * * * *" if args.every == 1 else f"*/{args.every} * * * *"
        kept += [
            f"{schedule} {shlex.join(check_command)} >> {shlex.quote(str(home / 'monitor.log'))} 2>&1 # {marker}",
            f"*/{max(5, args.every * 3)} * * * * {shlex.join(watchdog_command)} >> {shlex.quote(str(home / 'watchdog.log'))} 2>&1 # {marker}"
        ]
        completed = subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, capture_output=True)
        if completed.returncode:
            raise MonitorError(f"创建 crontab 失败: {completed.stderr}")
    write_json(home / f"job-{slug}.json", {"name": args.name, "everyMinutes": args.every, "arguments": check_cli_args(args), "createdAt": utc_now()})
    print(json.dumps({"created": args.name, "everyMinutes": args.every}, ensure_ascii=False))


def remove_schedule(name: str) -> None:
    slug = task_slug(name)
    if platform.system() == "Windows":
        for task_name in [f"AppleStockMonitor-{slug}", f"AppleStockWatchdog-{slug}"]:
            subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
    else:
        marker = f"apple-stock-monitor:{slug}"
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines()
        kept = [line for line in existing if marker not in line]
        subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True, check=True)
    for path in monitor_home().glob(f"*{slug}*"):
        if path.is_file() and path.name.startswith(("run-", "watchdog-", "job-")):
            path.unlink()
    print(json.dumps({"removed": name}, ensure_ascii=False))


def show_status() -> None:
    home = monitor_home()
    jobs = [read_json(path, {}) for path in home.glob("job-*.json")]
    value = {"home": str(home), "configured": bool(load_config().get("barkUrl") or os.environ.get("APPLE_STOCK_BARK_URL")), "state": read_json(home / "state.json", {}), "jobs": jobs}
    print(json.dumps(value, ensure_ascii=False, indent=2))


def add_monitor_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--city")
    parser.add_argument("--scope", choices=["china"])
    parser.add_argument("--model", required=True)
    parser.add_argument("--capacity")
    parser.add_argument("--color")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Monitor Apple Retail pickup inventory")
    commands = parser.add_subparsers(dest="command", required=True)
    configure = commands.add_parser("configure")
    configure.add_argument("--bark-url", required=True)
    configure.add_argument("--test", action="store_true")
    refresh = commands.add_parser("catalog-refresh")
    refresh.set_defaults(refresh_catalog=True)
    check = commands.add_parser("check")
    add_monitor_filters(check)
    check.add_argument("--refresh-catalog", action="store_true")
    watch = commands.add_parser("watchdog")
    watch.add_argument("--max-age", type=int, default=5)
    commands.add_parser("status")
    schedule = commands.add_parser("schedule")
    schedule_commands = schedule.add_subparsers(dest="schedule_command", required=True)
    create = schedule_commands.add_parser("create")
    create.add_argument("--name", required=True)
    create.add_argument("--every", type=int, default=1)
    add_monitor_filters(create)
    remove = schedule_commands.add_parser("remove")
    remove.add_argument("--name", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "configure":
            save_config(args.bark_url, args.test)
            print(json.dumps({"configured": True, "tested": args.test}, ensure_ascii=False))
        elif args.command == "catalog-refresh":
            products = refresh_catalog()
            print(json.dumps({"products": len(products), "updatedAt": utc_now()}, ensure_ascii=False))
        elif args.command == "check":
            run_check(args)
        elif args.command == "watchdog":
            watchdog(args.max_age)
        elif args.command == "status":
            show_status()
        elif args.command == "schedule" and args.schedule_command == "create":
            install_schedule(args)
        elif args.command == "schedule" and args.schedule_command == "remove":
            remove_schedule(args.name)
        return 0
    except MonitorError as exc:
        if args.command == "check":
            record_failure(str(exc))
        print(json.dumps({"error": str(exc), "at": utc_now()}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
