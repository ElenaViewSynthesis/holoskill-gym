from __future__ import annotations

import unittest

from src.workload import count_matches


class CountMatchesTests(unittest.TestCase):
    def test_counts_all_matching_occurrences(self) -> None:
        self.assertEqual(count_matches([1, 2, 1, 4], [1, 4]), 3)

    def test_accepts_generators(self) -> None:
        self.assertEqual(count_matches((value for value in [1, 2, 3]), [2, 3]), 2)


if __name__ == "__main__":
    unittest.main()
