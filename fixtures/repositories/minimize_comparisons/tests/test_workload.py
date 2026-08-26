from __future__ import annotations

import unittest

from src.workload import deduplicate


class DeduplicateTests(unittest.TestCase):
    def test_preserves_first_occurrence_order(self) -> None:
        self.assertEqual(deduplicate([3, 1, 3, 2, 1]), [3, 1, 2])

    def test_accepts_generators(self) -> None:
        self.assertEqual(deduplicate(value for value in ["a", "a", "b"]), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
