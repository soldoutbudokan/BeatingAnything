import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("devig_conj", ROOT / "tools/devig_thescore_sgp_conjunctions.py")
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def atom(var, line, player, mid, over_id, under_id):
    return {"var": var, "line": line, "player": player, "marketId": mid, "name": f"{player or 'Game'} {var}",
            "over": {"selectionId": over_id, "name": "Over", "decimal": 1.9}, "under": {"selectionId": under_id, "name": "Under", "decimal": 1.9}}


def base(var, op, thr, market="m", sel="s", price="+100"):
    return {"market": market, "selection": sel, "price": price, "var": var, "op": op, "threshold": thr, "id": f"{var}{thr}"}


class CellSearchTests(unittest.TestCase):
    def test_football_exact_cell_when_fanduel_has_both_lines(self):
        row = {"sport": "football", "space": "football_yards", "player": "Christian McCaffrey",
               "base": [base("S", ">=", 90), base("R", "<=", 54)], "stack": []}
        two_way = [atom("S", 89.5, "Christian McCaffrey", "734.1", 1, 2), atom("R", 54.5, "Christian McCaffrey", "734.2", 3, 4), atom("C", 35.5, "Christian McCaffrey", "734.3", 5, 6)]
        cell = dc.best_cell(row, two_way)
        self.assertEqual(cell["relation"], "exact")
        self.assertEqual(cell["target"], "OU")
        self.assertEqual([m["var"] for m in cell["markets"]], ["S", "R"])
        self.assertEqual(dc.cell_runners(cell, "OU"), [{"marketId": "734.1", "selectionId": 1}, {"marketId": "734.2", "selectionId": 4}])

    def test_football_subset_when_fanduel_rushing_line_is_tighter(self):
        row = {"sport": "football", "space": "football_yards", "player": "Christian McCaffrey", "base": [base("S", ">=", 90), base("R", "<=", 54)], "stack": []}
        two_way = [atom("S", 89.5, "Christian McCaffrey", "734.1", 1, 2), atom("R", 49.5, "Christian McCaffrey", "734.2", 3, 4)]
        cell = dc.best_cell(row, two_way)
        self.assertEqual(cell["relation"], "subset")  # S>=90 & R<=49 lies inside S>=90 & R<=54

    def test_football_crossed_when_only_components_exist(self):
        row = {"sport": "football", "space": "football_yards", "player": "MarShawn Lloyd", "base": [base("S", ">=", 90), base("R", "<=", 28)], "stack": []}
        two_way = [atom("R", 27.5, "MarShawn Lloyd", "734.1", 1, 2), atom("C", 35.5, "MarShawn Lloyd", "734.2", 3, 4)]
        cell = dc.best_cell(row, two_way)
        self.assertEqual(cell["relation"], "crossed")
        self.assertEqual(cell["target"], "UO")  # rushing under, receiving over is the nearest cell

    def test_other_players_markets_are_ignored(self):
        row = {"sport": "football", "space": "football_yards", "player": "MarShawn Lloyd", "base": [base("S", ">=", 90), base("R", "<=", 28)], "stack": []}
        two_way = [atom("R", 27.5, "Josh Jacobs", "734.1", 1, 2), atom("C", 35.5, "Josh Jacobs", "734.2", 3, 4)]
        self.assertIsNone(dc.best_cell(row, two_way))

    def test_team_space_moneyline_and_team_total(self):
        row = {"sport": "football", "space": "team", "player": None, "base": [base("result", "<", 0), base("team_H", ">=", 29)], "stack": []}
        two_way = [atom("result", None, None, "734.1", 1, 2), atom("team_H", 28.5, None, "734.2", 3, 4), atom("total", 45.5, None, "734.3", 5, 6)]
        cell = dc.best_cell(row, two_way)
        self.assertEqual(cell["relation"], "exact")
        self.assertEqual(cell["target"], "UO")  # away wins = moneyline 'under', home team total over
        self.assertEqual(dc.cell_runners(cell, cell["target"]), [{"marketId": "734.1", "selectionId": 2}, {"marketId": "734.2", "selectionId": 3}])

    def test_away_spread_maps_to_home_margin(self):
        row = {"sport": "football", "space": "team", "player": None, "base": [base("margin_A", ">=", 8), base("team_A", "<=", 18)], "stack": []}
        two_way = [atom("margin_H", -7.5, None, "734.1", 1, 2), atom("margin_H", -3.5, None, "734.2", 3, 4), atom("team_A", 18.5, None, "734.3", 5, 6)]
        cell = dc.best_cell(row, two_way)
        self.assertEqual(cell["relation"], "exact")  # away by 8+ = home margin <= -8 = under -7.5; away total under 18.5
        self.assertEqual(cell["target"], "UU")
        self.assertEqual(cell["markets"][0]["marketId"], "734.1")

    def test_whole_lines_are_skipped(self):
        row = {"sport": "football", "space": "team", "player": None, "base": [base("result", "<", 0), base("team_H", ">=", 29)], "stack": []}
        two_way = [atom("result", None, None, "734.1", 1, 2), atom("team_H", 29.0, None, "734.2", 3, 4)]
        self.assertIsNone(dc.best_cell(row, two_way))


class DevigTests(unittest.TestCase):
    def test_attach_ev_uses_target_cell(self):
        rec = {"stack_quote": {"decimal": 9.54}, "base_quote": {"decimal": 5.83}}
        cell = {"relation": "exact", "target": "OU", "markets": []}
        d = dc.attach_ev(rec, cell, {"OO": 2.27, "OU": 6.15, "UO": 6.5, "UU": 2.23})
        self.assertAlmostEqual(sum(1 / x for x in (2.27, 6.15, 6.5, 2.23)) - 1, d["hold"] - 1, places=9)
        self.assertEqual(d["bound"], "estimate")
        self.assertAlmostEqual(d["stack_ev_power"], 9.54 * d["p_power"] - 1)
        self.assertLess(d["p_power"], 1 / 6.15)

    def test_manual_partition_path(self):
        row = {"sport": "football", "space": "football_yards", "player": "X", "base": [base("S", ">=", 90), base("R", "<=", 54)], "stack": [],
               "stack_quote": {"decimal": 9.54}, "base_quote": {"decimal": 5.83}}
        d = dc.partition_ev(row, {"lines": {"S": 89.5, "R": 54.5}, "OO": 127, "OU": 515, "UO": 550, "UU": 123, "target": "OU"})
        self.assertEqual(d["relation"], "exact")
        self.assertEqual(d["fd_cells"]["OU"], "+515")


if __name__ == "__main__":
    unittest.main()
