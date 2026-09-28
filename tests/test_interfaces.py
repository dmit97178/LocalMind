"""Tests for core interface contracts."""

from src.core import interfaces


def test_backend_interfaces_are_abstract() -> None:
    for interface_type in [
        interfaces.ModelBackend,
        interfaces.MemoryBackend,
        interfaces.ToolBackend,
        interfaces.SafetyBackend,
        interfaces.CloudAdvisoryBackend,
        interfaces.EvolutionBackend,
    ]:
        assert interface_type.__abstractmethods__
        try:
            interface_type()
        except TypeError:
            pass
        else:
            raise AssertionError(f"{interface_type.__name__} should be abstract")


def test_model_capabilities_are_explicit_v1_fields() -> None:
    capabilities = interfaces.ModelCapabilities(
        supports_structured_output=True,
        max_context_tokens=8192,
        local_only=True,
    )

    assert capabilities.supports_structured_output is True
    assert capabilities.max_context_tokens == 8192
    assert capabilities.local_only is True


def test_detect_topic_relation_documents_allowed_values() -> None:
    docstring = interfaces.MemoryBackend.detect_topic_relation.__doc__

    assert docstring is not None
    assert "same_topic" in docstring
    assert "new_topic" in docstring
    assert "shift_with_reference" in docstring
    assert "ambiguous" in docstring
