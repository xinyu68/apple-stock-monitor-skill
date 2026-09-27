import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).parents[1] / "apple-stock-monitor" / "scripts" / "apple_stock_monitor.py"
SPEC = importlib.util.spec_from_file_location("apple_stock_monitor", SCRIPT)
monitor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(monitor)


class AppleStockMonitorTest(unittest.TestCase):
    def test_extracts_nested_product_json(self):
        page = '<script>window.PRODUCT_SELECTION_BOOTSTRAP={"productSelectionData":{"products":[{"partNumber":"A}B"}],"displayValues":{}}};</script>'
        value = monitor.extract_object_after_key(page, "productSelectionData")
        self.assertEqual(value["products"][0]["partNumber"], "A}B")

    def test_normalizes_model_capacity_color(self):
        data = {
            "products": [{
                "partNumber": "MJT84CH/A", "familyType": "iphone18promax",
                "dimensionCapacity": "256gb", "dimensionScreensize": "6_9inch",
                "dimensionColor": "silver"
            }],
            "displayValues": {
                "dimensionCapacity": {"256gb": {"value": "256 GB"}},
                "dimensionScreensize": {"6_9inch": {"value": "iPhone 18 Pro Max 6.9 英寸显示屏"}},
                "dimensionColor": {"silver": {"value": "银色"}}
            }
        }
        product = monitor.normalize_products("iphone-18-pro", data)[0]
        self.assertEqual(product["model"], "iPhone 18 Pro Max")
        self.assertEqual(product["capacity"], "256 GB")
        self.assertEqual(product["color"], "银色")
        self.assertEqual(product["partNumber"], "MJT84CH/A")

    def test_keeps_iphone_17_and_17e_as_distinct_models(self):
        base = monitor.normalize_products("iphone-17", {
            "products": [{"partNumber": "BASE", "familyType": "iphone17"}],
            "displayValues": {}
        })[0]
        compact = monitor.normalize_products("iphone-17e", {
            "products": [{"partNumber": "E", "familyType": "iphone17e"}],
            "displayValues": {}
        })[0]
        self.assertEqual(base["model"], "iPhone 17")
        self.assertEqual(compact["model"], "iPhone 17e")

        original = monitor.load_catalog
        monitor.load_catalog = lambda force=False: [base, compact]
        try:
            matches = monitor.resolve_products("iPhone 17", None, None)
        finally:
            monitor.load_catalog = original
        self.assertEqual([item["partNumber"] for item in matches], ["BASE"])

    def test_old_catalog_schema_is_refreshed(self):
        original_home = monitor.monitor_home
        original_refresh = monitor.refresh_catalog
        with tempfile.TemporaryDirectory() as directory:
            monitor.monitor_home = lambda: Path(directory)
            monitor.write_json(Path(directory) / "catalog.json", {
                "products": [{"partNumber": "STALE"}]
            })
            monitor.refresh_catalog = lambda: [{"partNumber": "FRESH"}]
            try:
                products = monitor.load_catalog()
            finally:
                monitor.monitor_home = original_home
                monitor.refresh_catalog = original_refresh
        self.assertEqual(products, [{"partNumber": "FRESH"}])

    def test_removes_apple_footnote_markers(self):
        self.assertEqual(monitor.clean_html("256 GB 脚注 1"), "256 GB")

    def test_resolves_exact_variant(self):
        original = monitor.load_catalog
        monitor.load_catalog = lambda force=False: [
            {"model": "iPhone 18 Pro Max", "capacity": "256 GB", "color": "银色", "partNumber": "S"},
            {"model": "iPhone 18 Pro Max", "capacity": "512 GB", "color": "银色", "partNumber": "L"},
            {"model": "iPhone 18 Pro", "capacity": "256 GB", "color": "银色", "partNumber": "P"}
        ]
        try:
            matches = monitor.resolve_products("iPhone 18 Pro Max", "256 G", "银色")
        finally:
            monitor.load_catalog = original
        self.assertEqual([item["partNumber"] for item in matches], ["S"])

    def test_parses_store_status_without_hiding_unknown(self):
        products = [{"partNumber": "A", "title": "Phone A", "buyUrl": "https://apple.example/buy"}]
        stores = [{
            "storeNumber": "R388", "storeName": "三里屯", "city": "北京",
            "partsAvailability": {"A": {"pickupDisplay": "available", "messageTypes": {"regular": {"storePickupQuote": "今天可取货"}}}}
        }]
        result = monitor.parse_results(stores, products, "北京")
        self.assertEqual(result[0]["status"], "available")
        self.assertEqual(result[0]["quote"], "今天可取货")
        self.assertEqual(monitor.classify_part(None), "unknown")

    def test_filters_results_by_exact_store_name_or_number(self):
        products = [{"partNumber": "A", "title": "Phone A", "buyUrl": "https://apple.example/buy"}]
        stores = [
            {
                "storeNumber": "R320", "storeName": "三里屯", "city": "北京",
                "partsAvailability": {"A": {"pickupDisplay": "available"}}
            },
            {
                "storeNumber": "R448", "storeName": "王府井", "city": "北京",
                "partsAvailability": {"A": {"pickupDisplay": "available"}}
            }
        ]

        by_name = monitor.parse_results(stores, products, "北京", "Apple 三里屯")
        by_number = monitor.parse_results(stores, products, "北京", "r448")

        self.assertEqual([item["storeNumber"] for item in by_name], ["R320"])
        self.assertEqual([item["storeNumber"] for item in by_number], ["R448"])

    def test_store_filter_does_not_fuzzily_match_multiple_stores(self):
        products = [{"partNumber": "A", "title": "Phone A", "buyUrl": "https://apple.example/buy"}]
        stores = [
            {"storeNumber": "R1", "storeName": "西单大悦城", "city": "北京", "partsAvailability": {}},
            {"storeNumber": "R2", "storeName": "朝阳大悦城", "city": "北京", "partsAvailability": {}}
        ]

        self.assertEqual(monitor.parse_results(stores, products, "北京", "大悦城"), [])

    def test_available_alert_uses_thirty_minute_cooldown_across_jobs(self):
        pushes = []
        original_home = monitor.monitor_home
        original_push = monitor.bark_push
        original_time = monitor.time.time
        with tempfile.TemporaryDirectory() as directory:
            now = [1000.0]
            monitor.monitor_home = lambda: Path(directory)
            monitor.bark_push = lambda *args, **kwargs: pushes.append((args, kwargs))
            monitor.time.time = lambda: now[0]
            try:
                first = {
                    "storeNumber": "R1", "storeName": "门店一", "city": "北京",
                    "partNumber": "A", "product": "iPhone A", "status": "available",
                    "quote": "今天可取货", "buyUrl": "https://apple.example/a"
                }
                second = {
                    "storeNumber": "R2", "storeName": "门店二", "city": "上海",
                    "partNumber": "B", "product": "iPhone B", "status": "available",
                    "quote": "今天可取货", "buyUrl": "https://apple.example/b"
                }
                monitor.record_success([first])
                monitor.record_success([second])
                monitor.record_success([first])
                self.assertEqual(len(pushes), 2)

                now[0] = 2799.0
                monitor.record_success([first])
                self.assertEqual(len(pushes), 2)

                now[0] = 2800.0
                monitor.record_success([first])
                self.assertEqual(len(pushes), 3)

                monitor.record_success([{**first, "status": "unavailable"}])
                monitor.record_success([first])
                self.assertEqual(len(pushes), 4)
            finally:
                monitor.monitor_home = original_home
                monitor.bark_push = original_push
                monitor.time.time = original_time

    def test_bark_push_requires_success_code(self):
        with patch.object(monitor, "load_config", return_value={"barkUrl": "https://api.day.app/test-secret"}):
            with patch.object(monitor, "request_json", return_value={"code": 200}) as request:
                monitor.bark_push("库存提醒", "测试")
            self.assertEqual(request.call_args.kwargs["payload"]["title"], "库存提醒")
            for response in ({}, {"code": 400}):
                with patch.object(monitor, "request_json", return_value=response):
                    with self.assertRaisesRegex(monitor.MonitorError, "未返回成功码"):
                        monitor.bark_push("库存提醒", "测试")

    def test_bark_network_error_redacts_key(self):
        secret = "test-secret"
        with patch.object(monitor, "load_config", return_value={"barkUrl": f"https://api.day.app/{secret}"}):
            with patch.object(monitor, "request_json", side_effect=OSError(f"https://api.day.app/{secret} failed")):
                with self.assertRaises(monitor.MonitorError) as error:
                    monitor.bark_push("库存提醒", "测试")
        self.assertNotIn(secret, str(error.exception))


if __name__ == "__main__":
    unittest.main()
