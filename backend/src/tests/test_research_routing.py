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
        "Explain the ranking approach",
        "Rewrite this paragraph",
        "Summarize yesterday's meeting",
        "I need paper towels",
        "Find paper plates",
        "Help me with paper towels",
        "I want paper cups",
        "Review saved paper towels",
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


@pytest.mark.parametrize("product", ["towel", "plate", "bag", "cup"])
@pytest.mark.parametrize("prefix", ["Find", "Help me with"])
def test_singular_household_paper_compounds_are_not_academic_requests(prefix, product):
    signal = ResearchRoutingParser().parse(f"{prefix} paper {product}")

    assert signal.decision == "none"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Review existing literature",
        "Review my saved papers",
        "Review current materials",
        "Review our memory",
        "Review experiment logs",
        "Review research notes",
    ],
)
def test_review_existing_research_is_not_a_fresh_research_request(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "review_existing"
    assert signal.needs_clarify is False


@pytest.mark.parametrize("message", ["Review notes", "Review my notes"])
def test_review_notes_is_existing_research_review(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "review_existing"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Review papers about graph reconstruction",
        "Review three very relevant papers",
        "Review peer reviewed papers",
    ],
)
def test_bare_review_requests_require_clarification(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5


@pytest.mark.parametrize(
    "message",
    [
        "Review recent papers",
        "Review latest literature",
        "Review new studies",
    ],
)
def test_review_with_freshness_language_is_allowed(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


def test_existing_review_combined_with_fresh_retrieval_is_allowed():
    signal = ResearchRoutingParser().parse(
        "Review existing papers and find new papers"
    )

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


def test_ambiguous_review_combined_with_explicit_retrieval_is_allowed():
    signal = ResearchRoutingParser().parse("Review papers and find new papers")

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Recent papers about graph reconstruction",
        "Latest literature on graph reconstruction",
        "New papers about graph reconstruction",
    ],
)
def test_standalone_fresh_research_phrases_are_allowed(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "allow"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    ["No recent papers", "Not latest literature", "Never new papers"],
)
def test_negated_standalone_fresh_research_phrases_are_denied(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "deny"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    ["Recent notes about papers", "New experiment logs about papers"],
)
def test_fresh_markers_do_not_cross_unrelated_material_nouns(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "none"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    [
        "Review a paper about our method",
        "Review papers comparing our method",
        "Review papers and write notes",
    ],
)
def test_direct_bare_review_remains_ambiguous(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5


def test_existing_review_is_bound_to_its_direct_object():
    signal = ResearchRoutingParser().parse(
        "Review existing papers with recent notes"
    )

    assert signal.decision == "review_existing"
    assert signal.needs_clarify is False


@pytest.mark.parametrize(
    "message",
    ["Review recent evidence", "Review latest methods", "Review new method"],
)
def test_review_freshness_with_non_collection_target_remains_ambiguous(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "conflict"
    assert signal.needs_clarify is True
    assert signal.confidence <= 0.5


@pytest.mark.parametrize("message", ["Recent evidence", "Latest methods"])
def test_standalone_freshness_requires_a_collection_target(message):
    signal = ResearchRoutingParser().parse(message)

    assert signal.decision == "none"
    assert signal.needs_clarify is False


def test_negated_review_is_denied():
    signal = ResearchRoutingParser().parse("Do not review literature")

    assert signal.decision == "deny"
    assert signal.needs_clarify is False


def test_existing_review_takes_precedence_over_fresh_retrieval_denial():
    signal = ResearchRoutingParser().parse(
        "Review saved papers; do not find new papers"
    )

    assert signal.decision == "review_existing"
    assert signal.needs_clarify is False


def test_signal_contract_is_bounded_to_routing_fields():
    signal = ResearchRoutingSignal(decision="allow", confidence=1.0)

    assert signal.model_dump() == {
        "decision": "allow",
        "needs_clarify": False,
        "confidence": 1.0,
    }
