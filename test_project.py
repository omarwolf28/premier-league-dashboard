"""Offline checks: py -m unittest -v."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import scraper


class ScraperTests(unittest.TestCase):
    def test_standings_validation(self):
        table, _, _ = scraper._sample_data()
        self.assertEqual(len(scraper._finish_table(table)), 20)
        table.loc[0, "P"] = 999
        with self.assertRaises(ValueError):
            scraper._finish_table(table)

    def test_player_team_and_numeric_sort(self):
        source = pd.DataFrame({"Name": ["A. PlayerHull City", "B. PlayerArsenal"], "Goals": [2, 10]})
        result = scraper._scrape_players("goals", [source])
        self.assertEqual(result.Goals.tolist(), [10, 2])
        self.assertEqual(result.iloc[1].Team, "Hull City")
        self.assertEqual(result.iloc[1].Player, "A. Player")

    def test_failed_refresh_preserves_cache(self):
        table, _, _ = scraper._sample_data()
        with tempfile.TemporaryDirectory() as directory, patch.object(scraper, "DATA_DIR", Path(directory)), patch.dict(os.environ, {"PL_DEMO": "0"}), patch.object(scraper, "scrape_bbc_table", return_value=table), patch.object(scraper, "_get_tables", side_effect=RuntimeError("offline")):
            first = scraper.load_data()
            self.assertIn("BBC Sport", first[3])
            original = (Path(directory) / "table.json").read_bytes()
            with patch.object(scraper, "scrape_bbc_table", side_effect=RuntimeError("offline")), patch.object(scraper, "scrape_espn_table", side_effect=RuntimeError("offline")):
                cached = scraper.load_data()
            self.assertIn("CACHED", cached[3])
            self.assertTrue(cached[1].empty)
            self.assertEqual(original, (Path(directory) / "table.json").read_bytes())
            pd.testing.assert_frame_equal(first[0], cached[0])

    def test_demo_never_requests_network(self):
        with patch.dict(os.environ, {"PL_DEMO": "1"}), patch.object(scraper.requests, "get") as get:
            result = scraper.load_data()
            self.assertIn("DEMO", result[3])
            get.assert_not_called()


class DashboardTests(unittest.TestCase):
    def test_layout_and_figures(self):
        import app
        client = app.server.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/_dash-layout").status_code, 200)
        table, scorers, assists = scraper._sample_data()
        data = {"table": table.to_dict("records"), "scorers": scorers.to_dict("records"), "assists": assists.to_dict("records")}
        self.assertEqual(len(app.scorers_fig(data, 3).data[0].x), 3)
        points = app.points_fig(data, [table.iloc[0].Team])
        self.assertEqual(sum(len(trace.x) for trace in points.data), 1)
        self.assertEqual(len(app.goals_fig(data, "GF").data[0].x), 20)
        self.assertEqual(len(app.summary(data)), 4)
        for fn in (app.show_table, app.summary, app.team_options):
            fn(None)
        app.scorers_fig(None, 10)
        app.points_fig(None, [])
        app.goals_fig(None, "GF")


if __name__ == "__main__":
    unittest.main()
