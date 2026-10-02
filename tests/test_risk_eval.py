import numpy as np
import yaml

from xrpl_input_credit.sim.model import Config
from xrpl_input_credit.sim.risk_eval import COLUMNS, SEASONS, panel


def test_panel_features_use_only_earlier_seasons():
    sim = yaml.safe_load(open("params.yaml"))["simulation"]
    cfg = Config.from_params(sim, ret=3.58, leakage=0.3, seasons=SEASONS, farmers=300, villages=5)
    data = panel(cfg, 3)
    first = data["season"] == 0
    # Columns: log land, loans, defaults, on-ledger diversions, all diversions.
    assert (data["X"][first][:, 1:] == 0).all()
    # A farmer's earlier-loan count can never exceed the number of earlier seasons.
    assert (data["X"][:, 1] <= data["season"]).all()
    # On-ledger diversion is a subset of all diversion.
    assert (data["X"][:, 3] <= data["X"][:, 4]).all()


def test_feature_sets_are_nested_except_the_off_ledger_swap():
    assert set(COLUMNS["land"]) < set(COLUMNS["history"]) < set(COLUMNS["ledger"])
    assert set(COLUMNS["history"]) < set(COLUMNS["all_div"])
    assert np.isin(4, COLUMNS["all_div"]) and not np.isin(4, COLUMNS["ledger"])
