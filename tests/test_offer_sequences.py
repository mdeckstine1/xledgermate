"""AccountOffers sequence extraction for cancel path."""

from connectors.xrpl_connector import XRPLConnector


def test_offer_field_from_dict() -> None:
    offer = {"seq": 104566211, "TakerGets": "1000000", "TakerPays": {"value": "1"}}
    assert XRPLConnector._offer_field(offer, "seq", "Sequence") == 104566211


def test_coerce_issued_amount_dict() -> None:
    class FakeAmt:
        value = "12.5"
        currency = "524C555344000000000000000000000000000000"
        issuer = "rIssuer"

    out = XRPLConnector._coerce_ledger_amount(FakeAmt())
    assert out["value"] == "12.5"
    assert out["currency"] == FakeAmt.currency
