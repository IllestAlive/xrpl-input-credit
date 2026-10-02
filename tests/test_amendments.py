from xrpl_input_credit.ledger.amendments import amendment_id


def test_amendment_id_matches_known_ledger_value():
    # ID as reported by a testnet `feature` call on 2026-10-02.
    assert amendment_id("fixNFTokenReserve") == (
        "03BDC0099C4E14163ADA272C1B6F6FABB448CC3E51F522F978041E4B57D9158C"
    )
