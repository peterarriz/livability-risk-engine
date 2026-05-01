import unittest

from fastapi import BackgroundTasks

from backend.app.routes import score as score_route


class BatchScoreParityTests(unittest.TestCase):
    def setUp(self):
        self._original_score_live = score_route._score_live

    def tearDown(self):
        score_route._score_live = self._original_score_live

    def _install_fake_live_scorer(self):
        calls = []

        def fake_score_live(address, coords=None):
            calls.append((address, coords))
            return {
                "address": address,
                "livability_score": 91,
                "disruption_score": 9,
                "confidence": "HIGH",
                "severity": {"noise": "LOW", "traffic": "LOW", "dust": "LOW"},
                "top_risks": ["No material disruption signals found nearby"],
                "explanation": "No material near-term disruption signals were found.",
                "mode": "live",
                "fallback_reason": None,
                "latitude": coords[0] if coords else 40.7484,
                "longitude": coords[1] if coords else -73.9857,
                "nearby_signals": [{"source": "test"}],
            }

        score_route._score_live = fake_score_live
        return calls

    def test_json_batch_scores_valid_rows_and_rejects_obvious_invalid_address(self):
        calls = self._install_fake_live_scorer()

        response = score_route.post_score_batch(
            score_route.BatchScoreRequest(
                addresses=["350 5th Ave, New York, NY", "zzzzzasdfg"]
            ),
            BackgroundTasks(),
        )

        self.assertEqual(response["scored"], 1)
        self.assertEqual(response["failed"], 1)

        valid, invalid = response["results"]
        self.assertEqual(valid["livability_score"], 91)
        self.assertEqual(valid["disruption_score"], 9)
        self.assertIsNone(valid["error"])
        self.assertNotIn("nearby_signals", valid)

        self.assertEqual(invalid["address"], "zzzzzasdfg")
        self.assertEqual(invalid["error"], "address_not_found")
        self.assertIsNone(invalid["livability_score"])
        self.assertIsNone(invalid["disruption_score"])

        self.assertEqual(calls, [("350 5th Ave, New York, NY", None)])

    def test_json_batch_canonical_aliases_resolve_to_same_demo_row(self):
        calls = self._install_fake_live_scorer()

        response = score_route.post_score_batch(
            score_route.BatchScoreRequest(
                addresses=[
                    "1600 W Chicago Ave, Chicago, IL",
                    "1600 West Chicago Avenue, Chicago, IL",
                ]
            ),
            BackgroundTasks(),
        )

        self.assertEqual(response["scored"], 2)
        self.assertEqual(response["failed"], 0)
        self.assertEqual(
            [row["address"] for row in response["results"]],
            [
                "1600 W Chicago Ave, Chicago, IL 60622",
                "1600 W Chicago Ave, Chicago, IL 60622",
            ],
        )
        self.assertEqual(response["results"][0]["livability_score"], response["results"][1]["livability_score"])
        self.assertEqual(response["results"][0]["disruption_score"], response["results"][1]["disruption_score"])
        self.assertEqual(
            calls,
            [
                ("1600 W Chicago Ave, Chicago, IL 60622", (41.8956, -87.6606)),
                ("1600 W Chicago Ave, Chicago, IL 60622", (41.8956, -87.6606)),
            ],
        )

    def test_csv_address_extraction_handles_quoted_and_unquoted_comma_addresses(self):
        expected = [
            "1600 W Chicago Ave, Chicago, IL",
            "1600 West Chicago Avenue, Chicago, IL",
            "350 5th Ave, New York, NY",
            "zzzzzasdfg",
        ]
        quoted = "\n".join(
            [
                "address",
                '"1600 W Chicago Ave, Chicago, IL"',
                '"1600 West Chicago Avenue, Chicago, IL"',
                '"350 5th Ave, New York, NY"',
                '"zzzzzasdfg"',
            ]
        )
        unquoted = "\n".join(
            [
                "address",
                "1600 W Chicago Ave, Chicago, IL",
                "1600 West Chicago Avenue, Chicago, IL",
                "350 5th Ave, New York, NY",
                "zzzzzasdfg",
            ]
        )

        self.assertEqual(score_route._addresses_from_csv_text(quoted), expected)
        self.assertEqual(score_route._addresses_from_csv_text(unquoted), expected)

    def test_csv_address_column_preserves_quoted_address_in_multi_column_file(self):
        text = "\n".join(
            [
                "account,address,notes",
                'Acme,"350 5th Ave, New York, NY",pilot row',
            ]
        )

        self.assertEqual(
            score_route._addresses_from_csv_text(text),
            ["350 5th Ave, New York, NY"],
        )

    def test_csv_failure_row_has_blank_score_fields_and_error(self):
        self._install_fake_live_scorer()

        row = score_route._result_to_csv_row(score_route._score_one("zzzzzasdfg"))

        self.assertEqual(row["address"], "zzzzzasdfg")
        self.assertEqual(row["livability_score"], "")
        self.assertEqual(row["disruption_score"], "")
        self.assertEqual(row["confidence"], "")
        self.assertEqual(row["severity_noise"], "")
        self.assertEqual(row["severity_traffic"], "")
        self.assertEqual(row["severity_dust"], "")
        self.assertEqual(row["error"], "address_not_found")


if __name__ == "__main__":
    unittest.main()
