from core.perception import BUILT_IN_PROFILES
from utils.profile_request import consume_profile_request, write_profile_request


def test_profile_request_round_trip(tmp_path, monkeypatch) -> None:
    import utils.profile_request as pr

    path = tmp_path / "profile_request.json"
    monkeypatch.setattr(pr, "PROFILE_REQUEST_PATH", path)

    write_profile_request("profit_mode")
    assert path.is_file()

    name = consume_profile_request(known_profiles=set(BUILT_IN_PROFILES.keys()))
    assert name == "profit_mode"
    assert not path.exists()

    assert consume_profile_request(known_profiles=set(BUILT_IN_PROFILES.keys())) is None
