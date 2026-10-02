from xrpl_input_credit.ledger.scenarios import Outcome, to_markdown


def test_unexpected_result_is_flagged_in_table():
    ok = Outcome("S1", "a -> b", "tesSUCCESS", "tesSUCCESS", "-")
    bad = Outcome("S2", "a -> c", "tecNO_PERMISSION", "tesSUCCESS", "L1")
    table = to_markdown([ok, bad])
    assert ok.matches and not bad.matches
    assert "**(unexpected)**" not in table.splitlines()[2]
    assert "**(unexpected)**" in table.splitlines()[3]
