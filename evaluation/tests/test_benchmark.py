import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('benchmark',Path(__file__).resolve().parents[1]/'benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

class BenchmarkTests(unittest.TestCase):
    def samples(self, warm=2):
        return ([{'variant':'baseline','cache_state':'disabled','install_seconds':v} for v in [4,5,6,7]] + [{'variant':'cached','cache_state':'cold','install_seconds':100}] + [{'variant':'cached','cache_state':'warm','install_seconds':warm} for _ in range(3)])

    def test_cold_cache_is_excluded_from_warm_median(self):
        result=benchmark.summarize(self.samples())
        self.assertEqual(result['baseline_median_seconds'],5.5)
        self.assertEqual(result['warm_median_seconds'],2)
        self.assertEqual(result['cold_seconds'],100)

    def test_slower_result_stays_negative(self):
        self.assertLess(benchmark.summarize(self.samples(warm=8))['improvement_percent'],0)

    def test_insufficient_samples_are_not_published(self):
        with self.assertRaises(ValueError): benchmark.summarize(self.samples()[:-1])
