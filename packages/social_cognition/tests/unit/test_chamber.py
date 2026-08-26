from __future__ import annotations

from hosaka_social.clock import FakeClock
from hosaka_social.config import SocialConfig
from hosaka_social.models import CandidateKind, CandidateStatus
from hosaka_social.simulation import make_candidate
from hosaka_social.social.chamber import Chamber, candidate_utility


def test_relevance_decays_on_interval() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    chamber.offer(make_candidate("note", clock=clock, relevance=1.0, importance=1.0))
    assert chamber.current is not None
    clock.advance(5)
    assert chamber.decay(clock.monotonic())
    assert chamber.current.relevance == 0.94
    assert chamber.current.importance == 0.98


def test_candidate_expires() -> None:
    clock = FakeClock()
    cfg = SocialConfig()
    chamber = Chamber(cfg, clock)
    chamber.offer(
        make_candidate(
            "joke",
            clock=clock,
            humor_value=0.9,
            importance=0.1,
        )
    )
    assert chamber.current is not None
    clock.advance(cfg.chamber.expiration.humor_seconds + 0.01)
    expired = chamber.expire(clock.monotonic())
    assert expired is not None
    assert expired.status is CandidateStatus.DISCARDED
    assert chamber.current is None


def test_stronger_replaces_weaker() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    weak = make_candidate("weak", clock=clock, relevance=0.4, importance=0.3)
    strong = make_candidate("strong", clock=clock, relevance=0.95, importance=0.9, urgency=0.4)
    chamber.offer(weak)
    evicted, action = chamber.offer(strong)
    assert action == "replaced"
    assert evicted is weak
    assert chamber.current is strong
    assert candidate_utility(strong) > candidate_utility(weak) + 0.15


def test_weaker_does_not_replace_stronger() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    strong = make_candidate("strong", clock=clock, relevance=0.95, importance=0.9)
    weak = make_candidate("weak", clock=clock, relevance=0.4, importance=0.3)
    chamber.offer(strong)
    rejected, action = chamber.offer(weak)
    assert action == "rejected_weaker"
    assert rejected is weak
    assert chamber.current is strong


def test_interrupted_re_chambers_once() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    cand = make_candidate("anyway", clock=clock, topic_id="retro")
    chamber.offer(cand)
    assert chamber.current is not None
    chamber.current.status = CandidateStatus.SPEAKING
    assert chamber.re_chamber_interrupted(chamber.current, ["retro"]) is True
    assert chamber.current is not None
    assert chamber.current.attempts == 1
    assert chamber.current.kind is CandidateKind.INTERRUPTED_THOUGHT
    chamber.current.status = CandidateStatus.SPEAKING
    assert chamber.re_chamber_interrupted(chamber.current, ["retro"]) is False
    assert chamber.current is None


def test_topic_change_discards_on_rechamber() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    cand = make_candidate("anyway", clock=clock, topic_id="retro")
    chamber.offer(cand)
    assert chamber.current is not None
    chamber.current.status = CandidateStatus.SPEAKING
    assert chamber.re_chamber_interrupted(chamber.current, ["fuel"]) is False
    assert chamber.current is None


def test_direct_response_outranks_chamber() -> None:
    clock = FakeClock()
    chamber = Chamber(SocialConfig(), clock)
    thought = make_candidate("later", clock=clock, relevance=0.99, importance=0.99)
    direct = make_candidate(
        "now",
        clock=clock,
        kind=CandidateKind.DIRECT_RESPONSE,
        relevance=0.2,
        importance=0.2,
    )
    chamber.offer(thought)
    evicted, action = chamber.offer(direct)
    assert action == "replaced_direct_priority"
    assert evicted is thought
    assert chamber.current is direct
