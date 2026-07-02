import pytest

from agent_team.research_routing import ResearchRoutingParser, ResearchRoutingSignal


@pytest.mark.parametrize(
    "message",
    [
        "I don't need papers",
        "I don’t need papers",
        "I do not need papers",
        "Do not search papers",
        "Find no papers",
        "Never search for papers",
        "Not search for papers",
    ],
)
def test_explicit_research_negation_is_denied(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "deny"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Find recent papers",
        "Recommend three relevant papers",
        "Show me papers",
        "I need literature",
        "Find papers about creating new agent architectures",
        "Search for ideal graph reconstruction methods",
    ],
)
def test_explicit_research_requests_are_allowed(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Do not search literature; find recent papers",
        "Find papers but do not search literature",
        "Search for studies and find no papers",
        "Do not review articles, yet recommend relevant evidence",
        "Find papers and never search literature",
        "Find papers and not search literature",
    ],
)
def test_mixed_allow_and_deny_requests_are_conflicts(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True


def test_parallel_allow_requests_remain_allowed():
    signal = ResearchRoutingParser().parse(
        "Find recent papers and recommend three relevant studies"
    )

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


def test_parallel_deny_requests_remain_denied():
    signal = ResearchRoutingParser().parse(
        "Do not search papers and do not review literature"
    )

    assert signal.decision == "deny"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Explain this function",
        "Rewrite this paragraph",
        "Read this code",
        "I need paper towels",
        "Find paper plates",
    ],
)
def test_non_research_messages_have_no_routing_signal(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "none"
    assert signal.needs_clarify is False
    assert signal.confidence == 1.0


@pytest.mark.parametrize(
    "message",
    [
        "Help me with papers about graph reconstruction",
        "I want literature about graph reconstruction",
    ],
)
def test_ambiguous_academic_requests_require_clarification(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5


def test_ambiguous_clause_caps_conflict_confidence():
    signal = ResearchRoutingParser().parse("Find papers; help me with literature")

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5


def test_household_paper_compound_does_not_hide_later_academic_target():
    signal = ResearchRoutingParser().parse("Find paper towels and studies")

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


def test_signal_contract_is_bounded_to_routing_fields():
    signal = ResearchRoutingSignal(decision="allow", confidence=1.0)

    assert signal.model_dump() == {
        "decision": "allow",
        "needs_clarify": False,
        "confidence": 1.0,
    }
