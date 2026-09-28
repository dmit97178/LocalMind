"""Two-stage capability routing and fail-closed decisions."""

from dataclasses import replace
from pathlib import Path

from src.core.control_policy import CloudControlState, ControlPolicy, evaluate_cloud_admission
from src.core.intent_resolver import IntentResolver
from src.core.schemas import (
    IntentCandidate,
    MinimalContext,
    ParamInstanceCheck,
    ToolCallDraft,
    ToolCapability,
    ToolDef,
)
from src.memory.in_memory_backend import InMemoryMemoryBackend
from src.tools.weather_tools import WEATHER_TOOL_DEF
from tests.test_intent_resolver import ScriptedModelBackend

_WEATHER = WEATHER_TOOL_DEF
_CAPABILITY = ToolCapability("weather.current", "Get current weather", ("weather.current",))


def _accept_instance(_: str) -> bool:
    return True


def _context(input_text: str) -> MinimalContext:
    return MinimalContext("system", current_input=input_text,
                          tool_defs=(_WEATHER,), capabilities=(_CAPABILITY,))


def _response(**fields: object) -> dict:
    response = {
        "state": "READY", "intent_type": "weather", "entities": {},
        "missing_info": [], "risk_draft": "normal", "model_confidence": 0.9,
        "tool_intent": "none", "tool_call": None,
    }
    response.update(fields)
    return response


def test_routed_intent_requires_second_model_round_and_only_selected_tool_is_shown() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(capability_id="none", tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "南京"},
        }),
    ])
    candidate = IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("南京天气怎么样"))

    assert candidate.capability_id == "weather.current"
    assert candidate.capability_resolution == "routed"
    assert candidate.tool_call == ToolCallDraft("weather.current", {"location": "南京"})
    assert len(model.prompts) == 2
    assert "Available local tools" not in model.prompts[0]
    assert "Available local tools" in model.prompts[1]
    assert "UNTRUSTED EXTERNAL REFERENCE" not in model.prompts[1]


def test_model_invented_location_is_rejected_before_execution() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "北京"},
        }),
    ])
    candidate = IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("南京天气怎么样"))

    assert candidate.tool_call is None
    assert candidate.tool_call_resolution == "param_not_from_input"
    assert ControlPolicy().decide(candidate, resolution_exhausted=False,
                                  tool_defs=(_WEATHER,), capabilities=(_CAPABILITY,)).reason == "param_not_from_input"


def test_partial_overlap_does_not_authorize_model_invented_location() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "今天公司的内部项目"},
        }),
    ])

    candidate = IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("今天查天气"))

    assert candidate.tool_call is None
    assert candidate.tool_call_resolution == "param_not_from_input"


def test_whole_input_weather_location_is_treated_as_missing() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "今天天气怎么样"},
        }),
    ])

    candidate = IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("今天天气怎么样"))
    action = ControlPolicy().decide(
        candidate, resolution_exhausted=False,
        tool_defs=(_WEATHER,), capabilities=(_CAPABILITY,),
    )

    assert candidate.tool_call == ToolCallDraft("weather.current", {})
    assert candidate.tool_call_resolution == "resolved"
    assert candidate.param_instance_rejected == ("location",)
    assert action.action == "ASK_USER"
    assert action.reason == "param_missing"


def test_weather_location_instance_check_rejects_time_word_and_accepts_place() -> None:
    from src.core.tool_validation import rejected_instance_params

    assert rejected_instance_params(
        {"location": "今天"}, _WEATHER, current_input="今天查天气",
    ) == ("location",)
    assert rejected_instance_params(
        {"location": "南京市"}, _WEATHER, current_input="南京市天气怎么样",
    ) == ()


def test_whole_input_rejection_is_declaration_driven() -> None:
    from src.core.tool_validation import rejected_instance_params

    parameters = {
        "type": "object",
        "properties": {"content": {"type": "string"}},
        "required": ["content"],
    }
    content_tool = ToolDef(
        "demo.content", "Store content", parameters, supply_by_echo=("content",),
    )
    entity_tool = replace(
        content_tool,
        name="demo.entity",
        param_instance_checks={
            "content": ParamInstanceCheck(_accept_instance, reject_whole_input=True),
        },
    )

    assert rejected_instance_params(
        {"content": "完整输入"}, content_tool, current_input="完整输入",
    ) == ()
    assert rejected_instance_params(
        {"content": "完整输入"}, entity_tool, current_input="完整输入",
    ) == ("content",)


def test_instance_check_declaration_is_not_rendered_and_tool_def_is_stable() -> None:
    from src.core.tool_validation import render_tool_catalog

    without_check = replace(_WEATHER, param_instance_checks={})

    assert render_tool_catalog((_WEATHER,)) == render_tool_catalog((without_check,))
    assert "_is_location_instance" not in render_tool_catalog((_WEATHER,))
    assert replace(_WEATHER) == _WEATHER
    assert hash(replace(_WEATHER)) == hash(_WEATHER)


def test_unrouted_proposals_are_never_recovered_by_tool_name() -> None:
    for raw_capability, expected, reason in (
        ("none", "none", "capability_unrouted"),
        ("unsupported", "unavailable", "capability_unavailable"),
        ("invalid", "unrecognized", "capability_unavailable"),
        (None, "absent", "capability_unrouted"),
    ):
        response = _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "南京"},
        })
        if raw_capability is not None:
            response["capability_id"] = raw_capability
        candidate = IntentResolver(
            ScriptedModelBackend([response]), InMemoryMemoryBackend(), max_rounds=1,
        ).resolve(_context("南京天气"))

        assert candidate.capability_resolution == expected
        assert candidate.tool_call is None
        assert candidate.tool_call_resolution == "unrouted_tool"
        assert ControlPolicy().decide(
            candidate, resolution_exhausted=False, tool_defs=(_WEATHER,),
            capabilities=(_CAPABILITY,),
        ).reason == reason


def test_stage_one_cannot_execute_a_tool_without_stage_two() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current", tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "南京"},
        }),
    ])
    resolver = IntentResolver(model, InMemoryMemoryBackend(), max_rounds=1)

    candidate = resolver.resolve(_context("南京天气"))

    assert candidate.tool_call is None
    assert candidate.capability_resolution == "routed"
    assert len(model.prompts) == 1


def test_routed_capability_with_no_second_stage_call_fails_honestly(monkeypatch) -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call=None),
    ])
    memory = InMemoryMemoryBackend()
    retrieval_calls: list[int] = []
    retrieve = memory.retrieve

    def counting_retrieve(*args, **kwargs):
        retrieval_calls.append(1)
        return retrieve(*args, **kwargs)

    monkeypatch.setattr(memory, "retrieve", counting_retrieve)
    resolver = IntentResolver(model, memory)

    candidate = resolver.resolve(_context("南京天气"))

    assert len(model.prompts) == 2
    assert candidate.tool_call_resolution == "absent"
    assert not resolver.last_no_progress
    assert retrieval_calls == []
    assert ControlPolicy().decide(
        candidate, resolution_exhausted=False, tool_defs=(_WEATHER,),
        capabilities=(_CAPABILITY,),
    ).reason == "tool_call_missing"


def test_last_round_routing_does_not_call_model_beyond_budget() -> None:
    model = ScriptedModelBackend([
        _response(state="VAGUE", missing_info=["goal"], capability_id="none"),
        _response(capability_id="weather.current"),
    ])
    resolver = IntentResolver(model, InMemoryMemoryBackend(), max_rounds=2)

    candidate = resolver.resolve(_context("南京天气"))

    assert len(model.prompts) == 2
    assert candidate.tool_call is None
    assert candidate.capability_resolution == "routed"
    assert ControlPolicy().decide(
        candidate, resolution_exhausted=resolver.last_resolution_exhausted,
        tool_defs=(_WEATHER,), capabilities=(_CAPABILITY,),
    ).reason == "tool_call_missing"


def test_stage_one_schema_does_not_expose_tool_names() -> None:
    class SchemaModel(ScriptedModelBackend):
        def __init__(self, responses: list[dict]) -> None:
            super().__init__(responses)
            self.schemas: list[dict] = []

        def generate(self, prompt: str, response_schema: dict | None = None) -> dict:
            assert response_schema is not None
            self.schemas.append(response_schema)
            return super().generate(prompt, response_schema)

    model = SchemaModel([_response(capability_id="weather.current"), _response()])
    IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("天气"))

    def names(schema: dict) -> list[str]:
        return schema["properties"]["tool_call"]["properties"]["tool_name"]["enum"]

    assert names(model.schemas[0]) == []
    assert names(model.schemas[1]) == ["weather.current"]
    assert set(model.schemas[1]["properties"]) == {"tool_intent", "tool_call"}
    assert model.schemas[1]["required"] == ["tool_intent", "tool_call"]
    assert "capability_id" not in model.schemas[1]["properties"]
    assert "unchanged" not in model.prompts[1]
    assert "Cloud calibration" not in model.prompts[1]
    assert "risk_draft must" not in model.prompts[1]
    assert "Selected capability: weather.current" in model.prompts[1]
    assert "Available local tools" in model.prompts[1]
    assert "Current input: 天气" in model.prompts[1]
    assert "Do not use the whole user question as an argument" in model.prompts[1]


def test_stage_one_names_all_declared_capabilities_without_claiming_availability() -> None:
    model = ScriptedModelBackend([_response(capability_id="none")])

    IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("解释幂等性"))

    prompt = model.prompts[0]
    assert "weather.current: Get current weather" in prompt
    assert 'capability_id="weather.current"' in prompt
    assert "unsupported" in prompt
    assert "Choose unavailable" not in prompt


def test_stage_two_invalid_shape_is_not_collapsed_into_missing_call() -> None:
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        {"tool_intent": "local_action", "tool_call": {}},
    ])

    candidate = IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("天气"))

    assert candidate.capability_id == "weather.current"
    assert candidate.tool_call_resolution == "invalid_shape"
    assert ControlPolicy().decide(
        candidate, resolution_exhausted=False, tool_defs=(_WEATHER,),
        capabilities=(_CAPABILITY,),
    ).reason == "tool_call_invalid_shape"


def test_inactive_declared_capability_is_unavailable_without_model_status() -> None:
    from src.core.intent_resolver import _candidate_from_model_output

    candidate = _candidate_from_model_output(
        _response(capability_id="weather.current"),
        (), (_CAPABILITY,), "今天南京天气怎么样",
    )

    assert candidate.capability_id == "weather.current"
    assert candidate.capability_resolution == "unavailable"


def test_inactive_declared_capability_rejects_even_a_tool_draft() -> None:
    from src.core.intent_resolver import _candidate_from_model_output

    candidate = _candidate_from_model_output(
        _response(capability_id="weather.current", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "南京"},
        }),
        (), (_CAPABILITY,), "南京天气",
    )

    assert candidate.capability_id == "weather.current"
    assert candidate.capability_resolution == "unavailable"
    assert candidate.tool_call is None
    assert candidate.tool_call_resolution == "unrouted_tool"


def test_unsupported_request_retains_its_diagnostic_id() -> None:
    from src.core.intent_resolver import _candidate_from_model_output

    candidate = _candidate_from_model_output(
        _response(capability_id="unsupported"), (), (_CAPABILITY,), "查询航班实时状态",
    )

    assert candidate.capability_id == "unsupported"
    assert candidate.capability_resolution == "unavailable"


def test_routed_prompt_classifies_new_file_write_as_sensitive() -> None:
    model = ScriptedModelBackend([_response(capability_id="none")])

    IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("新建 notes.txt"))

    assert "Creating a new file inside the workspace requires confirmation and is sensitive" in model.prompts[0]
    assert "Creating a new file inside the workspace is also normal" not in model.prompts[0]


def test_open_routing_pure_answer_prompt_does_not_expose_test_tool() -> None:
    model = ScriptedModelBackend([_response(capability_id="none")])

    IntentResolver(model, InMemoryMemoryBackend()).resolve(_context("解释幂等性"))

    assert "system.echo" not in model.prompts[0]
    assert "Available local tools" not in model.prompts[0]


def test_disabled_routing_does_not_emit_capability_fields(tmp_path: Path, monkeypatch) -> None:
    from src.main import bootstrap
    from src.models.mock_backend import MockModelBackend
    from tests.test_main import RecordingEventSink
    from tests.test_p7_config import FixedWeatherProvider

    source = (Path(__file__).parents[1] / "config" / "default.toml").read_text(encoding="utf-8")
    disabled = tmp_path / "disabled.toml"
    disabled.write_text(source.replace("[capability_routing]\nenabled = true", "[capability_routing]\nenabled = false"), encoding="utf-8")
    off_sink = RecordingEventSink()
    on_sink = RecordingEventSink()
    off = bootstrap(
        str(disabled), model_backend_override=MockModelBackend(structured_response=_response(capability_id="none")),
        weather_provider_override=FixedWeatherProvider(), event_sink_override=off_sink,
    )
    on = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=MockModelBackend(structured_response=_response(capability_id="none")),
        weather_provider_override=FixedWeatherProvider(), event_sink_override=on_sink,
    )
    monkeypatch.setattr("src.main.time.perf_counter", lambda: 100.0)
    off.handle("解释幂等性", "same-session")
    on.handle("解释幂等性", "same-session")

    off_final = next(event.data for event in off_sink.events if event.stage == "intent_final")
    on_final = next(event.data for event in on_sink.events if event.stage == "intent_final")
    assert "capability_id" not in off_final
    assert "capability_resolution" not in off_final
    assert "param_instance_rejected" not in off_final
    assert "capability_id" not in off.last_turn_report()
    assert on_final["capability_resolution"] == "none"
    assert off.last_turn_report()["rounds_used"] == on.last_turn_report()["rounds_used"] == 1
    assert {
        key: value for key, value in on_final.items()
        if not key.startswith("capability_") and key != "param_instance_rejected"
    } == off_final
    off_dispatch = next(event.data for event in off_sink.events if event.stage == "dispatch_decision")
    on_dispatch = next(event.data for event in on_sink.events if event.stage == "dispatch_decision")
    assert off_dispatch == on_dispatch
    assert off._pending_tool_input is None
    assert [event.stage for event in off_sink.events] == [event.stage for event in on_sink.events]
    for off_event, on_event in zip(off_sink.events, on_sink.events, strict=True):
        without_capabilities = {
            key: value for key, value in on_event.data.items()
            if not key.startswith("capability_") and key != "param_instance_rejected"
        }
        assert off_event.data.keys() == without_capabilities.keys()
        assert off_event.data == without_capabilities


def test_unavailable_capability_does_not_auto_escalate_or_execute() -> None:
    from src.core.schemas import ConsultationProposal

    candidate = replace(
        IntentCandidate(state="READY", intent_type="weather", model_confidence=0.9),
        capability_resolution="unavailable",
        consultation_proposal=ConsultationProposal(True, "current_information", 0.9),
    )
    cloud = CloudControlState(True, provider_available=True, remaining_turns=3)

    assert evaluate_cloud_admission(candidate, cloud).gate_result == "not_evaluated"
    action = ControlPolicy().decide(candidate, cloud, resolution_exhausted=False,
                                    capabilities=())
    assert (action.action, action.reason) == ("PLAN_LOCAL", "capability_unavailable")

    forced = CloudControlState(
        True, force_cloud=True, provider_available=True,
        remaining_turns=3, has_task_text=True,
    )
    assert evaluate_cloud_admission(candidate, forced).gate_result == "admitted_forced"
    assert ControlPolicy().decide(
        candidate, forced, resolution_exhausted=False, capabilities=(),
    ).action == "REQUEST_CLOUD"


def test_app_returns_honest_unavailable_reply_without_tool_execution(tmp_path: Path) -> None:
    from src.main import _CAPABILITY_UNAVAILABLE_REPLY, bootstrap
    from src.models.mock_backend import MockModelBackend
    from tests.test_main import RecordingEventSink

    default = (Path(__file__).parents[1] / "config" / "p6_legacy.example.toml").read_text(encoding="utf-8")
    config_path = tmp_path / "route.toml"
    config_path.write_text(
        default.replace("[execution]", "[capability_routing]\nenabled = true\n\n[execution]")
        .replace('"system.echo", ', ""), encoding="utf-8"
    )
    model = MockModelBackend(structured_response=_response(capability_id="unsupported"))
    sink = RecordingEventSink()
    app = bootstrap(str(config_path), model_backend_override=model, event_sink_override=sink)

    reply = app.handle("今天南京天气怎么样", "weather-session")

    assert reply == _CAPABILITY_UNAVAILABLE_REPLY
    assert app.last_turn_report()["reason"] == "capability_unavailable"
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"
    assert not app.executor.audit_log
    assert app._pending_tool_input is None
    assert not [event for event in sink.events if event.stage in {"tool_execution", "cloud_consult"}]


def test_weather_availability_is_registry_fact_with_identical_first_stage_prompt(
    tmp_path: Path,
) -> None:
    from src.main import _CAPABILITY_UNAVAILABLE_REPLY, bootstrap
    from tests.test_p7_config import FixedWeatherProvider

    source = (Path(__file__).parents[1] / "config" / "default.toml").read_text(
        encoding="utf-8"
    )
    off_config = tmp_path / "weather-off.toml"
    off_config.write_text(
        source.replace('provider = "open_meteo"', 'provider = "none"'), encoding="utf-8"
    )
    on_model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        {"tool_intent": "local_action", "tool_call": None},
    ])
    off_model = ScriptedModelBackend([_response(capability_id="weather.current")])
    on = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=on_model,
        weather_provider_override=FixedWeatherProvider(),
    )
    off = bootstrap(str(off_config), model_backend_override=off_model)

    on.handle("今天南京天气怎么样", "weather-on")
    off_reply = off.handle("今天南京天气怎么样", "weather-off")

    assert on_model.prompts[0] == off_model.prompts[0]
    assert len(on_model.prompts) == 2
    assert len(off_model.prompts) == 1
    assert on.last_turn_report()["capability_resolution"] == "routed"
    assert off.last_turn_report()["capability_resolution"] == "unavailable"
    assert off.last_turn_report()["capability_id"] == "weather.current"
    assert off_reply == _CAPABILITY_UNAVAILABLE_REPLY
    assert not off.executor.audit_log


def test_app_rejects_tool_outside_selected_capability_without_execution() -> None:
    from src.main import _CAPABILITY_UNROUTED_REPLY, bootstrap
    from tests.test_main import RecordingEventSink
    from tests.test_p7_config import FixedWeatherProvider

    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "file.write", "arguments": {"path": 123, "unknown": "bad"},
        }),
    ])
    sink = RecordingEventSink()
    app = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=model,
        weather_provider_override=FixedWeatherProvider(), event_sink_override=sink,
    )

    reply = app.handle("南京天气怎么样", "irrelevant-session")

    assert reply == _CAPABILITY_UNROUTED_REPLY
    assert app.last_turn_report()["reason"] == "capability_irrelevant"
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"
    assert not app.executor.audit_log
    assert not [event for event in sink.events if event.stage == "tool_execution"]


def test_secret_supplied_after_weather_followup_is_rejected_before_egress() -> None:
    from src.main import bootstrap
    from tests.test_main import RecordingEventSink

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def current_weather(self, location: str) -> dict:
            self.calls.append(location)
            return {"location": location, "source": "test"}

    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {},
        }),
    ])
    provider = CountingProvider()
    sink = RecordingEventSink()
    app = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=model, weather_provider_override=provider,
        event_sink_override=sink,
    )
    app.handle("今天天气怎么样", "secret-session")
    before = len(model.prompts)

    app.handle("sk-" + "A" * 25, "secret-session")

    assert len(model.prompts) == before
    assert provider.calls == []
    assert app.last_turn_report()["rounds_used"] == 0
    assert app.last_turn_report()["reply_provenance"] == "unfulfilled"
    assert app.executor.audit_log is not None
    assert app.executor.audit_log[-1].params_redacted == {"location": "***"}
    assert len([event for event in sink.events if event.stage == "tool_execution"]) == 1
    assert not [event for event in sink.events if event.stage == "cloud_consult"]
    assert "sk-" + "A" * 25 not in repr(sink.events)


def test_missing_weather_location_is_supplied_next_turn_without_model_call(tmp_path: Path) -> None:
    from src.main import bootstrap
    from tests.test_p7_config import FixedWeatherProvider

    default = (Path(__file__).parents[1] / "config" / "p6_legacy.example.toml").read_text(encoding="utf-8")
    config_path = tmp_path / "route.toml"
    config_path.write_text(
        default.replace("[execution]", "[capability_routing]\nenabled = true\n\n[execution]")
        .replace('whitelist = ["system.echo",', 'whitelist = ["weather.current",')
        .replace('[tools]\n', '[tools]\n\n[tools.weather]\nprovider = "open_meteo"\n'),
        encoding="utf-8",
    )
    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {"location": "今天天气怎么样"},
        }),
    ])
    app = bootstrap(
        str(config_path), model_backend_override=model,
        weather_provider_override=FixedWeatherProvider(),
    )

    first = app.handle("今天天气怎么样", "session-weather")
    assert app._pending_tool_input is not None
    assert app.last_turn_report()["param_instance_rejected"] == ("location",)
    before = len(model.prompts)
    second = app.handle("南京", "session-weather")

    assert "location" in first
    assert app._pending_tool_input is None
    assert "南京" in second
    assert len(model.prompts) == before == 2
    assert app.last_turn_report()["rounds_used"] == 0
    assert app.last_turn_report()["param_instance_rejected"] == ()
    assert app.last_turn_report()["reply_provenance"] == "executed"


def test_invalid_weather_followup_returns_to_model_without_egress() -> None:
    from src.main import bootstrap

    class CountingProvider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def current_weather(self, location: str) -> dict:
            self.calls.append(location)
            return {"location": location}

    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {},
        }),
        _response(capability_id="none"),
    ])
    provider = CountingProvider()
    app = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=model,
        weather_provider_override=provider,
    )
    app.handle("今天天气怎么样", "invalid-followup")
    before = len(model.prompts)

    app.handle("今天", "invalid-followup")

    assert len(model.prompts) > before
    assert provider.calls == []
    assert app._pending_tool_input is None
    assert app.last_turn_report()["rounds_used"] == 1
    assert app.last_turn_report()["reply_provenance"] != "executed"


def test_pending_weather_input_is_not_reused_by_another_session() -> None:
    from src.main import bootstrap
    from tests.test_p7_config import FixedWeatherProvider

    model = ScriptedModelBackend([
        _response(capability_id="weather.current"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {},
        }),
        _response(capability_id="none"),
        _response(capability_id="none"),
    ])
    app = bootstrap(
        str(Path(__file__).parents[1] / "config" / "default.toml"),
        model_backend_override=model, weather_provider_override=FixedWeatherProvider(),
    )
    app.handle("今天天气怎么样", "session-a")
    assert app._pending_tool_input is not None
    before = len(model.prompts)

    app.handle("南京", "session-b")

    assert len(model.prompts) > before
    assert app._pending_tool_input is None
    assert app.last_turn_report()["rounds_used"] >= 1
    assert not app.executor.audit_log

    before = len(model.prompts)
    app.handle("南京", "session-a")
    assert len(model.prompts) > before
    assert app._pending_tool_input is None
    assert not app.executor.audit_log


def test_disabled_routing_never_creates_pending_tool_input(tmp_path: Path) -> None:
    from src.main import bootstrap
    from tests.test_p7_config import FixedWeatherProvider

    source = (Path(__file__).parents[1] / "config" / "default.toml").read_text(encoding="utf-8")
    config = tmp_path / "disabled.toml"
    config.write_text(source.replace("[capability_routing]\nenabled = true", "[capability_routing]\nenabled = false"), encoding="utf-8")
    model = ScriptedModelBackend([
        _response(tool_intent="local_action", tool_call={
            "tool_name": "weather.current", "arguments": {},
        }),
        _response(tool_intent="none", tool_call=None),
    ])
    app = bootstrap(
        str(config), model_backend_override=model,
        weather_provider_override=FixedWeatherProvider(),
    )

    app.handle("今天天气怎么样", "off-session")
    assert app._pending_tool_input is None
    before = len(model.prompts)
    app.handle("南京", "off-session")
    assert len(model.prompts) > before
    assert app._pending_tool_input is None


def test_multiple_missing_echo_parameters_do_not_create_pending_state(
    tmp_path: Path, monkeypatch
) -> None:
    from src.main import bootstrap
    from src.tools import builtin_backend, registry

    definition = ToolDef(
        "demo.lookup", "Read two values",
        {"type": "object", "properties": {
            "first": {"type": "string"}, "second": {"type": "string"},
        }, "required": ["first", "second"]},
        supply_by_echo=("first", "second"),
    )
    monkeypatch.setitem(
        registry.BUILTIN_TOOLS, "demo.lookup",
        registry.RegisteredTool(definition, lambda params, _context: dict(params)),
    )
    monkeypatch.setattr(
        builtin_backend, "BUILTIN_CAPABILITIES",
        (*builtin_backend.BUILTIN_CAPABILITIES,
         ToolCapability("demo.lookup", "Read two values", ("demo.lookup",))),
    )
    source = (Path(__file__).parents[1] / "config" / "default.toml").read_text(encoding="utf-8")
    config = tmp_path / "demo.toml"
    config.write_text(
        source.replace(
            '"weather.current", "document.read", "file.search"]',
            '"demo.lookup"]',
        ),
        encoding="utf-8",
    )
    model = ScriptedModelBackend([
        _response(capability_id="demo.lookup"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "demo.lookup", "arguments": {},
        }),
    ])
    app = bootstrap(str(config), model_backend_override=model)

    reply = app.handle("查这两个值", "multi-session")

    assert "first" in reply and "second" in reply
    assert app._pending_tool_input is None
    assert app.last_turn_report()["reason"] == "param_missing"


def test_file_write_missing_content_never_enters_echo_supply_path(tmp_path: Path) -> None:
    from src.main import bootstrap
    from tests.test_p7_config import FixedWeatherProvider

    config = Path(__file__).parents[1] / "config" / "default.toml"
    model = ScriptedModelBackend([
        _response(capability_id="files.write"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "file.write", "arguments": {"path": "notes.txt"},
        }),
        _response(capability_id="none"),
    ])
    app = bootstrap(
        str(config), model_backend_override=model,
        weather_provider_override=FixedWeatherProvider(),
    )
    app.executor.tool_backend._workspace_root = tmp_path  # type: ignore[attr-defined]

    first = app.handle("写 notes.txt，内容稍后给你", "write-session")
    assert "content" in first
    assert app._pending_tool_input is None

    before = len(model.prompts)
    app.handle("改聊别的事情", "write-session")
    assert len(model.prompts) > before
    assert app.last_turn_report()["rounds_used"] >= 1
    assert not (tmp_path / "notes.txt").exists()


def test_new_registered_capability_runs_without_orchestrator_changes(
    tmp_path: Path, monkeypatch
) -> None:
    from src.main import bootstrap
    from src.tools import builtin_backend, registry

    definition = ToolDef(
        "demo.upper", "Uppercase text",
        {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
    )
    monkeypatch.setitem(
        registry.BUILTIN_TOOLS, "demo.upper",
        registry.RegisteredTool(definition, lambda params, _context: {"text": params["value"].upper()}),
    )
    monkeypatch.setattr(
        builtin_backend, "BUILTIN_CAPABILITIES",
        (*builtin_backend.BUILTIN_CAPABILITIES,
         ToolCapability("demo.text", "Transform text", ("demo.upper",))),
    )
    source = (Path(__file__).parents[1] / "config" / "default.toml").read_text(encoding="utf-8")
    config = tmp_path / "demo.toml"
    config.write_text(
        source.replace(
            '"weather.current", "document.read", "file.search"]',
            '"demo.upper"]',
        ),
        encoding="utf-8",
    )
    model = ScriptedModelBackend([
        _response(capability_id="demo.text"),
        _response(tool_intent="local_action", tool_call={
            "tool_name": "demo.upper", "arguments": {"value": "hello"},
        }),
    ])
    app = bootstrap(str(config), model_backend_override=model)

    reply = app.handle("把 hello 转成大写", "demo-session")

    assert "HELLO" in reply
    assert app.last_turn_report()["reply_provenance"] == "executed"
    assert len(model.prompts) == 2
    assert "demo.text" in model.prompts[0]
    assert "demo.upper" not in model.prompts[0]
    assert "demo.upper" in model.prompts[1]
