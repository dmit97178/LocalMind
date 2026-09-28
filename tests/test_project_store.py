"""P5 project-state ownership behavior."""

from dataclasses import asdict

from src.core.schemas import ProjectState
from src.memory.project_store import ProjectStore


class DictRecords:
    def __init__(self) -> None:
        self.records: dict[str, dict] = {}

    def get_project_record(self, project_id: str) -> dict | None:
        record = self.records.get(project_id)
        return None if record is None else dict(record)

    def put_project_record(self, record: dict) -> None:
        self.records[record["project_id"]] = dict(record)

    def list_project_ids(self) -> list[str]:
        return list(self.records)


def test_ensure_normalizes_explicit_project_and_creates_skeleton() -> None:
    store = ProjectStore(DictRecords(), auto_create=True, summary_max_chars=2000)

    project_id = store.resolve("unrelated text", "Client Launch 2026")
    state = store.ensure(project_id or "")

    assert project_id == "client-launch-2026"
    assert state is not None
    assert state.project_id == "client-launch-2026"
    assert state.title == "client-launch-2026"
    assert state.status == "active"


def test_manual_summary_is_not_replaced_by_automatic_update() -> None:
    records = DictRecords()
    store = ProjectStore(records, auto_create=True, summary_max_chars=20)
    store.ensure("client-launch")
    store.set_manual("client-launch", "summary", "Keep this summary")

    store.update_auto("client-launch", summary="automatic replacement", add_topic_tags=("launch",))

    state = store.load("client-launch")
    assert state is not None
    assert state.summary == "Keep this summary"
    assert state.topic_tags == ("launch",)


def test_resolve_requires_a_unique_title_or_tag_match() -> None:
    records = DictRecords()
    records.put_project_record(asdict(_state_record("alpha", "Shared plan", ("shared",))))
    records.put_project_record(asdict(_state_record("beta", "Other plan", ("shared",))))
    store = ProjectStore(records, auto_create=True, summary_max_chars=2000)

    assert store.resolve("continue the shared work", None) is None


def test_auto_create_false_and_unknown_auto_update_do_not_write_records() -> None:
    records = DictRecords()
    store = ProjectStore(records, auto_create=False, summary_max_chars=10)

    assert store.ensure("missing") is None
    store.update_auto("missing", summary="ignored")

    assert records.records == {}


def test_auto_summary_is_truncated_to_configured_limit() -> None:
    store = ProjectStore(DictRecords(), auto_create=True, summary_max_chars=5)
    store.ensure("alpha")

    store.update_auto("alpha", summary="123456")

    assert store.load("alpha").summary == "12345"  # type: ignore[union-attr]


def _state_record(project_id: str, title: str, tags: tuple[str, ...]) -> ProjectState:
    return ProjectState(
        project_id=project_id,
        title=title,
        goal="",
        constraints=(),
        status="active",
        summary="",
        topic_tags=tags,
        manual_overrides=frozenset(),
        created_at="2026-09-09T00:00:00+00:00",
        updated_at="2026-09-09T00:00:00+00:00",
    )
