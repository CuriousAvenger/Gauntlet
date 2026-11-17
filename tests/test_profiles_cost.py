from gauntlet import cost, profiles
from gauntlet.config import load_config


def test_detect_field():
    assert profiles.detect_field("Can quantum computers speed up fluid simulation?") == "math-physics-cs"
    assert profiles.detect_field("Does a higher minimum wage reduce unemployment?") == "economics-policy"
    assert profiles.detect_field("Is intermittent fasting good for treatment of diabetes?") == "medicine-biology"
    assert profiles.detect_field("Why did the Roman empire fall?") == "history-humanities"
    assert profiles.detect_field("What is the best Python web framework for latency?") == "software-engineering"
    assert profiles.detect_field("What makes a good picnic?") == "general"


def test_profile_roundtrip():
    text = profiles.draft_profile("Is ibuprofen safe with aspirin?", reader_level="student")
    p = profiles.parse_profile(text)
    assert p["field"] == "medicine-biology" and p["high_stakes"] is True and p["reader_level"] == "student"
    assert "systematic-review" in p["authoritative_kinds"]


def test_estimate_scales_with_depth():
    cfg = load_config()
    q, s, d = (cost.estimate(cfg, x)["total_usd"] for x in ("quick", "standard", "deep"))
    assert 0 < q < s < d
    for x in ("quick", "standard", "deep"):
        e = cost.estimate(cfg, x)
        assert e["total_usd"] <= e["budget_usd"], x


def test_stop_conditions(proj):
    stop, _ = cost.should_stop(proj)
    assert not stop
    cost.start_cycle(proj)
    cost.end_cycle(proj)
    stop, why = cost.should_stop(proj)   # standard depth: 1 cycle
    assert stop and "cycle limit" in why


def test_stale_cycles(proj):
    s = proj.state()
    s["targets"]["max_cycles"] = 10
    proj.save_state(s)
    for _ in range(3):
        cost.start_cycle(proj)
        cost.end_cycle(proj)
    stop, why = cost.should_stop(proj)
    assert stop and "no new evidence" in why


def test_pack_install(tmp_path):
    profiles.install_pack("quantum-readout", tmp_path / "pack")
    assert (tmp_path / "pack" / "mistakes.md").exists()
