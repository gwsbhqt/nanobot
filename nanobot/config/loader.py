"""Configuration loading utilities."""

import json
from pathlib import Path

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    return get_data_dir() / "config.json"


def get_config_example_path() -> Path:
    """Get the default example configuration file path."""
    return get_data_dir() / "config.example.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            return Config.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(
        by_alias=True,
        exclude_defaults=True,
        exclude_none=True,
    )
    data = _prune_empty(data)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def save_config_example(config_path: Path | None = None) -> Path:
    """Write a guided example config for manual onboarding."""
    path = config_path or get_config_example_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "agents": {
            "defaults": {
                "provider": "custom",
                "model": "gpt-5.3-codex",
                "workspace": ".nanobot/workspace",
            }
        },
        "providers": {
            "custom": {
                "apiKey": "YOUR_API_KEY",
                "apiBase": "https://your-openai-compatible-endpoint/v1",
            },
            "openrouter": {
                "apiKey": "sk-or-...",
            },
        },
        "channels": {
            "feishu": {
                "enabled": False,
                "appId": "cli_xxx",
                "appSecret": "xxx",
                "allowFrom": [],
                "reactEmoji": "THUMBSUP",
            }
        },
        "tools": {
            "web": {
                "search": {
                    "apiKey": "YOUR_BRAVE_SEARCH_API_KEY",
                    "maxResults": 5,
                }
            }
        },
    }

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return path


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data


def _prune_empty(value):
    """Recursively remove empty values from config payload."""
    if isinstance(value, dict):
        pruned = {k: _prune_empty(v) for k, v in value.items()}
        return {k: v for k, v in pruned.items() if v not in ("", None, [], {})}
    if isinstance(value, list):
        pruned = [_prune_empty(v) for v in value]
        return [v for v in pruned if v not in ("", None, [], {})]
    return value
