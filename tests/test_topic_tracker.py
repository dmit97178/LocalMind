"""P5 topic-state behavior."""

from src.core.topic_tracker import TopicTracker


def test_tracker_isolates_sessions_and_preserves_reference_anchor() -> None:
    tracker = TopicTracker()

    first_a = tracker.on_turn(
        "session-a", "Prepare quarterly budget", relation="new_topic", project_id="finance"
    )
    first_b = tracker.on_turn(
        "session-b", "Plan garden work", relation="new_topic", project_id="home"
    )
    referenced_a = tracker.on_turn(
        "session-a", "Continue with the earlier figures", relation="shift_with_reference", project_id="finance"
    )

    assert first_a.topic_label == "prepare-quarterly-budget"
    assert first_b.topic_label == "plan-garden-work"
    assert referenced_a.referenced_topic == "prepare-quarterly-budget"
    assert tracker.current_topic("session-b") == "plan-garden-work"


def test_tracker_clears_session_state_at_end_of_session() -> None:
    tracker = TopicTracker()
    tracker.on_turn("session-a", "Prepare report", relation="new_topic", project_id=None)

    tracker.end_session("session-a")

    assert tracker.current_topic("session-a") == ""
    assert tracker.current_project_id("session-a") is None
    assert tracker.topics_history("session-a") == ()


def test_project_switch_resets_label_without_rewriting_relation() -> None:
    tracker = TopicTracker()
    tracker.on_turn("session-a", "Prepare report", relation="new_topic", project_id="alpha")

    decision = tracker.on_turn(
        "session-a", "Prepare report", relation="same_topic", project_id="beta"
    )

    assert decision.relation == "same_topic"
    assert decision.project_switched is True
    assert decision.topic_label == "prepare-report"


def test_first_turn_forces_new_topic_and_ambiguous_never_carries_reference() -> None:
    tracker = TopicTracker()

    first = tracker.on_turn("session-a", "First report", relation="ambiguous", project_id=None)
    ambiguous = tracker.on_turn("session-a", "look at this", relation="ambiguous", project_id=None)

    assert first.relation == "new_topic"
    assert first.topic_label == "first-report"
    assert ambiguous.referenced_topic is None
    assert ambiguous.topic_label == "first-report"


def test_topics_history_keeps_distinct_labels_with_current_topic_last() -> None:
    tracker = TopicTracker()
    tracker.on_turn("session-a", "First report", relation="new_topic", project_id=None)
    tracker.on_turn("session-a", "still on it", relation="same_topic", project_id=None)
    tracker.on_turn("session-a", "Plan release", relation="new_topic", project_id=None)
    tracker.on_turn(
        "session-a", "return to report", relation="shift_with_reference", project_id=None
    )

    assert tracker.topics_history("session-a") == (
        "first-report",
        "plan-release",
        "return-to-report",
    )
