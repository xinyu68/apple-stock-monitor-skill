import importlib.util
import unittest
from pathlib import Path


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

    def test_china_schedule_rejects_aggressive_interval(self):
        args = monitor.build_parser().parse_args([
            "schedule", "create", "--name", "china", "--every", "1",
            "--scope", "china", "--model", "iPhone 18 Pro Max"
        ])
        with self.assertRaisesRegex(monitor.MonitorError, "不得小于 3"):
            monitor.install_schedule(args)


if __name__ == "__main__":
    unittest.main()
