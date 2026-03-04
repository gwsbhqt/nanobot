import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from nanobot.cli.commands import _make_provider, app
from nanobot.config.loader import _migrate_config, save_config, save_config_example
from nanobot.config.schema import Config
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


def test_onboard_existing_config_yes_overwrites_without_prompt(mock_paths):
    """--yes should overwrite existing config without interactive confirmation."""
    config_file, _config_example_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard", "--yes"])

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "Config reset to defaults" in result.stdout
    assert workspace_dir.exists()


def test_onboard_existing_config_refresh_without_prompt(mock_paths):
    """--refresh should keep existing values without interactive confirmation."""
    config_file, _config_example_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard", "--refresh"])

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()


def test_onboard_rejects_yes_and_refresh_together(mock_paths):
    """--yes and --refresh are mutually exclusive."""
    result = runner.invoke(app, ["onboard", "--yes", "--refresh"])

    assert result.exit_code == 1
    assert "mutually exclusive" in result.stdout


def test_config_matches_openrouter_provider_by_default():
    config = Config()
    config.agents.defaults.model = "google/gemini-3.1-flash-lite-preview"
    config.providers.openrouter.api_key = "sk-or-test"

    assert config.get_provider_name() == "openrouter"


def test_config_matches_openrouter_with_prefix():
    config = Config()
    config.agents.defaults.provider = "auto"
    config.agents.defaults.model = "openrouter/google/gemini-3.1-flash-lite-preview"
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
        default_model="google/gemini-3.1-flash-lite-preview",
    )

    resolved = provider._resolve_model("google/gemini-3.1-flash-lite-preview")

    assert resolved == "openrouter/google/gemini-3.1-flash-lite-preview"


def test_make_provider_passes_openrouter_proxy_from_config():
    config = Config()
    config.providers.openrouter.api_key = "sk-or-test"
    config.providers.openrouter.proxy = "http://127.0.0.1:7890"

    provider = _make_provider(config)

    assert provider.proxy == "http://127.0.0.1:7890"


def test_save_config_omits_defaults_and_empty_values(tmp_path):
    config_path = tmp_path / "config.json"

    save_config(Config(), config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload == {}


def test_save_config_keeps_only_non_default_values(tmp_path):
    config_path = tmp_path / "config.json"
    cfg = Config()
    cfg.providers.openrouter.api_key = "sk-or-test"

    save_config(cfg, config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload == {
        "providers": {
            "openrouter": {"apiKey": "sk-or-test"}
        }
    }


def test_save_config_example_contains_guided_fields(tmp_path):
    config_path = tmp_path / "config.example.json"

    save_config_example(config_path=config_path)

    with open(config_path, encoding="utf-8") as f:
        payload = json.load(f)

    assert payload["agents"]["defaults"]["provider"] == "openrouter"
    assert payload["agents"]["defaults"]["model"] == "google/gemini-3.1-flash-lite-preview"
    assert payload["agents"]["defaults"]["simpleModel"] == "google/gemini-2.5-flash-lite-preview-09-2025"
    assert payload["agents"]["defaults"]["complexModel"] == "google/gemini-3.1-flash-lite-preview"
    assert payload["agents"]["defaults"]["modelRouting"] == "auto"
    assert payload["providers"]["openrouter"]["apiKey"] == "sk-or-..."
    assert payload["providers"]["openrouter"]["proxy"] is None
    assert payload["tools"]["web"]["proxy"] is None
    assert payload["channels"]["feishu"]["enabled"] is False


def test_migrate_config_maps_openai_codex_provider_to_openrouter():
    payload = {
        "agents": {
            "defaults": {
                "provider": "openai_codex",
                "model": "google/gemini-3.1-flash-lite-preview",
            }
        }
    }

    migrated = _migrate_config(payload)

    assert migrated["agents"]["defaults"]["provider"] == "openrouter"


def test_migrate_config_maps_openai_codex_model_prefix():
    payload = {
        "agents": {
            "defaults": {
                "provider": "auto",
                "model": "openai-codex/gpt-5.1-codex",
            }
        }
    }

    migrated = _migrate_config(payload)

    assert migrated["agents"]["defaults"]["model"] == "google/gemini-3.1-flash-lite-preview"
    assert migrated["agents"]["defaults"]["complexModel"] == "google/gemini-3.1-flash-lite-preview"
    assert migrated["agents"]["defaults"]["simpleModel"] == "google/gemini-2.5-flash-lite-preview-09-2025"


def test_migrate_config_backfills_dual_model_fields():
    payload = {
        "agents": {
            "defaults": {
                "provider": "openrouter",
                "model": "google/gemini-3.1-flash-lite-preview",
            }
        }
    }

    migrated = _migrate_config(payload)

    assert migrated["agents"]["defaults"]["complexModel"] == "google/gemini-3.1-flash-lite-preview"
    assert migrated["agents"]["defaults"]["simpleModel"] == "google/gemini-2.5-flash-lite-preview-09-2025"
    assert migrated["agents"]["defaults"]["modelRouting"] == "auto"


def test_migrate_config_preserves_snake_case_dual_model_fields():
    payload = {
        "agents": {
            "defaults": {
                "provider": "openrouter",
                "simple_model": "google/gemini-2.5-flash-lite-preview-09-2025",
                "complex_model": "google/gemini-3.1-flash-lite-preview",
                "model_routing": "simple",
            }
        }
    }

    migrated = _migrate_config(payload)

    assert migrated["agents"]["defaults"]["simpleModel"] == "google/gemini-2.5-flash-lite-preview-09-2025"
    assert migrated["agents"]["defaults"]["complexModel"] == "google/gemini-3.1-flash-lite-preview"
    assert migrated["agents"]["defaults"]["modelRouting"] == "simple"
    assert migrated["agents"]["defaults"]["model"] == "google/gemini-3.1-flash-lite-preview"


def test_get_simple_and_complex_models_from_config_defaults():
    config = Config()

    assert config.get_simple_model() == "google/gemini-2.5-flash-lite-preview-09-2025"
    assert config.get_complex_model() == "google/gemini-3.1-flash-lite-preview"


def test_litellm_provider_parse_uses_refusal_when_content_empty():
    provider = LiteLLMProvider(
        api_key="sk-or-test",
        provider_name="openrouter",
        default_model="google/gemini-3.1-flash-lite-preview",
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


def test_litellm_provider_sets_proxy_env_when_configured(monkeypatch):
    proxy = "http://127.0.0.1:7890"
    for env_name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.delenv(env_name, raising=False)

    LiteLLMProvider(
        api_key="sk-or-test",
        provider_name="openrouter",
        default_model="google/gemini-3.1-flash-lite-preview",
        proxy=proxy,
    )

    for env_name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        assert os.environ[env_name] == proxy
