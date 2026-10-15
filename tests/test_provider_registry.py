"""Provider registry: one declaration per tool, waterfalls that stop on success."""
import unittest

from services import provider_registry as registry
from services.provider_registry import ProviderSpec, run_waterfall


def _spec(name, **overrides):
    fields = {"name": name, "label": name.title(),
              "datapoints": frozenset({"company_search"}),
              "keys": (f"{name.upper()}_KEY",)}
    fields.update(overrides)
    return ProviderSpec(**fields)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(registry._REGISTRY)
        registry._REGISTRY.clear()

    def tearDown(self):
        registry._REGISTRY.clear()
        registry._REGISTRY.update(self._saved)

    def test_a_provider_registers_with_one_call(self):
        registry.register(_spec("acme"))
        self.assertEqual(registry.get("acme").label, "Acme")
        self.assertIsNone(registry.get("nope"))

    def test_order_is_explicit_or_cost_based(self):
        registry.register(_spec("b", cost_weight=2))
        registry.register(_spec("a", cost_weight=1))
        self.assertEqual([s.name for s in registry.providers_for("company_search")],
                         ["a", "b"])
        self.assertEqual([s.name for s in registry.providers_for("company_search", order=["b", "a"])],
                         ["b", "a"])

    def test_unknown_names_in_order_are_ignored(self):
        registry.register(_spec("a"))
        self.assertEqual([s.name for s in registry.providers_for("company_search", order=["ghost", "a"])],
                         ["a"])

    def test_datapoints_select(self):
        registry.register(_spec("a"))
        registry.register(_spec("b", datapoints=frozenset({"verify"})))
        self.assertEqual([s.name for s in registry.providers_for("company_search")], ["a"])
        self.assertEqual([s.name for s in registry.providers_for("verify")], ["b"])


class WaterfallTests(unittest.TestCase):
    def key(self, item):
        return item.get("id") or None

    def warn(self, name, exc):
        return f"{name}: {exc}"

    def test_stops_once_the_target_is_met(self):
        calls = []

        def first():
            calls.append("first")
            return [{"id": "1"}, {"id": "2"}]

        def second():
            calls.append("second")
            return [{"id": "3"}]

        out = run_waterfall(
            [("first", first, (ValueError,)), ("second", second, (ValueError,))],
            target=2, key_fn=self.key, warn_fn=self.warn)
        self.assertEqual([i["id"] for i in out["results"]], ["1", "2"])
        self.assertEqual(calls, ["first"])
        self.assertIn({"provider": "second", "status": "skipped", "count": 0},
                      out["waterfall"])

    def test_misses_and_failures_move_on(self):
        def empty():
            return []

        def broken():
            raise ValueError("down")

        def good():
            return [{"id": "9"}]

        out = run_waterfall(
            [("empty", empty, (ValueError,)), ("broken", broken, (ValueError,)),
             ("good", good, (ValueError,))],
            target=5, key_fn=self.key, warn_fn=self.warn)
        self.assertEqual([i["id"] for i in out["results"]], ["9"])
        self.assertEqual([step["status"] for step in out["waterfall"]],
                         ["miss", "error", "hit"])
        self.assertTrue(any("down" in w for w in out["warnings"]))

    def test_duplicates_across_providers_count_once(self):
        out = run_waterfall(
            [("a", lambda: [{"id": "1"}], (ValueError,)),
             ("b", lambda: [{"id": "1"}, {"id": "2"}], (ValueError,))],
            target=10, key_fn=self.key, warn_fn=self.warn)
        self.assertEqual([i["id"] for i in out["results"]], ["1", "2"])

    def test_unexpected_errors_surface_instead_of_laundering(self):
        def broken():
            raise RuntimeError("programmer error")

        with self.assertRaises(RuntimeError):
            run_waterfall([("broken", broken, (ValueError,))],
                          target=5, key_fn=self.key, warn_fn=self.warn)

    def test_none_target_tries_everything(self):
        calls = []

        def each(name):
            calls.append(name)
            return []

        out = run_waterfall(
            [(name, (lambda n=name: lambda: each(n))(), (ValueError,))
             for name in ("a", "b", "c")],
            target=None, key_fn=self.key, warn_fn=self.warn)
        self.assertEqual(calls, ["a", "b", "c"])
        self.assertEqual(out["results"], [])


if __name__ == "__main__":
    unittest.main()
