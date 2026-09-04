"""Offline tests for the pure parts of preprocess.py. Run with: python -m unittest discover cirro"""

import unittest

from preprocess import incompatible_inputs, input_specs, library_signature


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


class InputSpecs(unittest.TestCase):
    """ds.metadata["inputs"] is what Cirro actually provides; there is no ds.inputs."""

    def test_reads_name_and_path(self):
        self.assertEqual(
            input_specs([{"id": "abc", "processId": "p",
                          "dataPath": "s3://bucket/datasets/abc",
                          "name": "VS76_Vir3_Dec2024_Z7"}]),
            [("VS76_Vir3_Dec2024_Z7", "s3://bucket/datasets/abc")],
        )

    def test_falls_back_to_the_id_when_unnamed(self):
        # Better a UUID label than a failed run.
        self.assertEqual(
            input_specs([{"id": "abc", "dataPath": "s3://bucket/datasets/abc"}]),
            [("abc", "s3://bucket/datasets/abc")],
        )

    def test_strips_a_trailing_slash_from_the_path(self):
        # The workflow appends data/... to it, so a doubled slash would not resolve.
        self.assertEqual(
            input_specs([{"id": "a", "name": "n", "dataPath": "s3://b/d/a/"}])[0][1],
            "s3://b/d/a",
        )

    def test_a_dataset_without_a_path_is_refused(self):
        with self.assertRaises(ValueError):
            input_specs([{"id": "abc", "name": "n"}])

    def test_order_is_preserved_so_names_match_paths_by_position(self):
        entries = [{"id": str(i), "name": f"run{i}", "dataPath": f"s3://b/{i}"}
                   for i in range(3)]
        self.assertEqual([name for name, _ in input_specs(entries)],
                         ["run0", "run1", "run2"])


if __name__ == "__main__":
    unittest.main()
