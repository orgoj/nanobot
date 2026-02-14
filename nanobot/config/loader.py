"""Configuration loading utilities."""

from pathlib import Path

import yaml

from nanobot.config.schema import Config


def get_config_path() -> Path:
    """Get the default configuration file path."""
    # Try YAML first, fallback to legacy formats
    yaml_path = Path.home() / ".nanobot" / "config.yaml"
    if yaml_path.exists():
        return yaml_path
    yml_path = Path.home() / ".nanobot" / "config.yml"
    if yml_path.exists():
        return yml_path
    # Legacy fallback (for migration period)
    return Path.home() / ".nanobot" / "config.json"


def get_data_dir() -> Path:
    """Get the nanobot data directory."""
    from nanobot.utils.helpers import get_data_path

    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from YAML file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path) as f:
                data = yaml.safe_load(f)
            if data is None:
                data = {}
            return Config.model_validate(data)
        except (yaml.YAMLError, ValueError) as e:
            print(f"Warning: Failed to load config from {path}: {e}")
            print("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to YAML file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump()

    with open(path, "w") as f:
        yaml.dump(
            data,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
