import pytest
from unittest.mock import patch
from config import load_config, load_yaml_path


@pytest.fixture(autouse=True)
def no_dotenv():
    """Prevent load_dotenv from loading the real .env file in tests."""
    with patch("config.load_dotenv"):
        yield


def test_load_config_with_all_vars(monkeypatch):
    monkeypatch.setenv("RRM_AI_PROVIDER", "openai")
    monkeypatch.setenv("RRM_AI_MODEL", "gpt-4o")
    monkeypatch.setenv("RRM_AI_API_KEY", "sk-test")
    monkeypatch.setenv("RRM_AI_YAML", "/tmp/test.yaml")

    cfg = load_config()
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4o"
    assert cfg.api_key == "sk-test"
    assert cfg.yaml_path == "/tmp/test.yaml"


def test_load_config_defaults(monkeypatch):
    monkeypatch.setenv("RRM_AI_API_KEY", "sk-test")
    monkeypatch.setenv("RRM_AI_YAML", "/tmp/test.yaml")
    monkeypatch.delenv("RRM_AI_PROVIDER", raising=False)
    monkeypatch.delenv("RRM_AI_MODEL", raising=False)

    cfg = load_config()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-sonnet-4-5-20250929"


def test_load_config_missing_api_key(monkeypatch):
    monkeypatch.delenv("RRM_AI_API_KEY", raising=False)
    monkeypatch.setenv("RRM_AI_YAML", "/tmp/test.yaml")

    with pytest.raises(ValueError, match="RRM_AI_API_KEY"):
        load_config()


def test_load_config_missing_yaml_path(monkeypatch):
    monkeypatch.setenv("RRM_AI_API_KEY", "sk-test")
    monkeypatch.delenv("RRM_AI_YAML", raising=False)

    with pytest.raises(ValueError, match="RRM_AI_YAML"):
        load_config()


def test_load_yaml_path_does_not_require_api_key(monkeypatch):
    monkeypatch.delenv("RRM_AI_API_KEY", raising=False)
    monkeypatch.setenv("RRM_AI_YAML", "/tmp/test.yaml")

    assert load_yaml_path() == "/tmp/test.yaml"
