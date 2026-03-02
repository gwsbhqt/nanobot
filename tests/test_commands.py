import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import app
from nanobot.config.loader import save_config, save_config_example
from nanobot.config.schema import Config
from nanobot.providers.custom_provider import CustomProvider
from nanobot.providers.litellm_provider import LiteLLMProvider
from nanobot.providers.registry import find_gateway

runner = CliRunner()


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    with patch("nanobot.config.loader.get_config_path") as mock_cp, \
         patch("nanobot.config.loader.get_config_example_path") as mock_ep, \
         patch("nanobot.config.loader.save_config") as mock_sc, \
         patch("nanobot.config.loader.save_config_example") as mock_se, \
         patch("nanobot.config.loader.load_config"), \
         patch("nanobot.utils.helpers.get_workspace_path") as mock_ws:

        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        config_example_file = base_dir / "config.example.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file
        mock_ep.return_value = config_example_file
        mock_ws.return_value = workspace_dir
        mock_sc.side_effect = lambda config: config_file.write_text("{}")
        mock_se.side_effect = lambda: (config_example_file.write_text("{}"), config_example_file)[1]

        yield config_file, config_example_file, workspace_dir

        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_onboard_fresh_install(mock_paths):
    """No existing config — should create from scratch."""
    config_file, config_example_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Created config" in result.stdout
    assert "Created workspace" in result.stdout
    assert "nanobot is ready" in result.stdout
    assert config_file.exists()
    assert config_example_file.exists()
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_existing_config_refresh(mock_paths):
    """Config exists, user declines overwrite — should refresh (load-merge-save)."""
    config_file, _config_example_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()
    assert (workspace_dir / "AGENTS.md").exists()


def test_onboard_existing_config_overwrite(mock_paths):
    """Config exists, user confirms overwrite — should reset to defaults."""
    config_file, _config_example_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="y\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "Config reset to defaults" in result.stdout
    assert workspace_dir.exists()


def test_onboard_existing_workspace_safe_create(mock_paths):
    """Workspace exists — should not recreate, but still add missing templates."""
    config_file, _config_example_file, workspace_dir = mock_paths
    workspace_dir.mkdir(parents=True)
    config_file.write_text("{}")

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Created workspace" not in result.stdout
    assert "Created AGENTS.md" in result.stdout
    assert (workspace_dir / "AGENTS.md").exists()


def test_config_matches_custom_provider_by_default():
    config = Config()
    config.agents.defaults.model = "gpt-5.3-codex"
    config.providers.custom.api_key = "test-key"
    config.providers.custom.api_base = "https://example.com/v1"

    assert config.get_provider_name() == "custom"


def test_config_matches_openrouter_with_prefix():
    config = Config()
    config.agents.defaults.provider = "auto"
    config.agents.defaults.model = "openrouter/gpt-5.3-codex"
    config.providers.openrouter.api_key = "sk-or-test"

    assert config.get_provider_name() == "openrouter"


def test_find_gateway_detects_openrouter_by_key_prefix():
    spec = find_gateway(api_key="sk-or-test")

    assert spec is not None
    assert spec.name == "openrouter"


def test_litellm_provider_gateway_adds_openrouter_prefix():
    provider = LiteLLMProvider(
        api_key="sk-or-test",
        provider_name="openrouter",
        default_model="gpt-5.3-codex",
    )

    resolved = provider._resolve_model("gpt-5.3-codex")

    assert resolved == "openrouter/gpt-5.3-codex"


def test_save_config_omits_defaults_and_empty_values(tmp_path):
    config_path = tmp_path / "config.json"

    save_config(Config(), config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload == {}


def test_save_config_keeps_only_non_default_values(tmp_path):
    config_path = tmp_path / "config.json"
    cfg = Config()
    cfg.providers.custom.api_key = "sk-test"
    cfg.providers.custom.api_base = "https://example.com/v1"

    save_config(cfg, config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload == {
        "providers": {
            "custom": {
                "apiKey": "sk-test",
                "apiBase": "https://example.com/v1",
            }
        }
    }


def test_save_config_example_contains_guided_fields(tmp_path):
    config_path = tmp_path / "config.example.json"

    save_config_example(config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["agents"]["defaults"]["provider"] == "custom"
    assert payload["providers"]["custom"]["apiKey"] == "YOUR_API_KEY"
    assert payload["providers"]["openrouter"]["apiKey"] == "sk-or-..."
    assert payload["channels"]["feishu"]["enabled"] is False


def test_custom_provider_parse_uses_refusal_when_content_empty():
    provider = CustomProvider(api_key="test", api_base="https://example.com/v1", default_model="gpt-5.3-codex")
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, refusal="I can not do that right now.", tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=None,
    )

    parsed = provider._parse(response)

    assert parsed.content == "I can not do that right now."
    assert parsed.finish_reason == "stop"


def test_litellm_provider_parse_uses_refusal_when_content_empty():
    provider = LiteLLMProvider(
        api_key="sk-or-test",
        provider_name="openrouter",
        default_model="gpt-5.3-codex",
    )
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, refusal="Refused", tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=None,
    )

    parsed = provider._parse_response(response)

    assert parsed.content == "Refused"
    assert parsed.finish_reason == "stop"
