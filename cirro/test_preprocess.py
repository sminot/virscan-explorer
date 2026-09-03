"""Offline tests for the pure parts of preprocess.py. Run with: python -m unittest discover cirro"""

import unittest

from preprocess import incompatible_inputs, library_signature


class LibrarySignature(unittest.TestCase):
    def test_parses_a_full_dataset_name(self):
        self.assertEqual(
            library_signature("VS78_Vir3_Dec2024_Z7"), ("Vir3", "Dec2024", "Z7")
        )

    def test_parses_a_fractional_threshold(self):
        self.assertEqual(
            library_signature("VS57_Vir3_Jan2023_Z3.5"), ("Vir3", "Jan2023", "Z3.5")
        )

    def test_threshold_is_optional(self):
        self.assertEqual(
            library_signature("VS81_Vir3_April2026"), ("Vir3", "April2026", None)
        )

    def test_unparseable_name_yields_none(self):
        self.assertIsNone(library_signature("cohort-rerun"))


class IncompatibleInputs(unittest.TestCase):
    def test_runs_sharing_a_library_and_threshold_are_mergeable(self):
        self.assertIsNone(
            incompatible_inputs(
                [
                    "VS76_Vir3_Dec2024_Z7",
                    "VS77_Vir3_Dec2024_Z7",
                    "VS78_Vir3_Dec2024_Z7",
                ]
            )
        )

    def test_a_single_run_is_mergeable(self):
        self.assertIsNone(incompatible_inputs(["VS76_Vir3_Dec2024_Z7"]))

    def test_different_libraries_are_refused(self):
        problem = incompatible_inputs(["VS78_Vir3_Dec2024_Z7", "VS78_CoV_Dec2024_Z7"])
        self.assertIsNotNone(problem)
        self.assertIn("Vir3", problem)
        self.assertIn("CoV", problem)

    def test_different_thresholds_are_refused(self):
        problem = incompatible_inputs(["VS57_Vir3_Jan2023_Z7", "VS57_Vir3_Jan2023_Z3.5"])
        self.assertIsNotNone(problem)
        self.assertIn("Z3.5", problem)

    def test_different_library_versions_are_refused(self):
        self.assertIsNotNone(
            incompatible_inputs(["VS78_Vir3_Dec2024_Z7", "VS78_Vir3_Dec2025_Z7"])
        )

    def test_unparseable_names_do_not_block_a_run(self):
        # A renamed dataset says nothing about comparability, so it must not veto.
        self.assertIsNone(
            incompatible_inputs(["VS76_Vir3_Dec2024_Z7", "my-reprocessed-run"])
        )


if __name__ == "__main__":
    unittest.main()
