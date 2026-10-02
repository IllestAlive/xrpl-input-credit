import yaml

from xrpl_input_credit.sim.model import Config
from xrpl_input_credit.sim.sensitivity import RANGES, configs


def test_every_range_brackets_its_base_value():
    sim = yaml.safe_load(open("params.yaml"))["simulation"]
    cust, self_ = configs(sim)
    for name, (_, lo, hi) in RANGES.items():
        base = {"leak_custodial": cust.leakage, "leak_self": self_.leakage}.get(name)
        if base is None:
            assert name in Config.__dataclass_fields__, name
            base = getattr(cust, name)
        assert lo <= base <= hi, (name, lo, base, hi)


def test_override_reaches_only_the_intended_field():
    sim = yaml.safe_load(open("params.yaml"))["simulation"]
    cust, self_ = configs(sim, "leak_self", 0.45)
    assert self_.leakage == 0.45 and cust.leakage == sim["leakage_by_custody"]["custodial"]
    cust, _ = configs(sim, "interest_rate", 0.2)
    assert cust.interest_rate == 0.2
