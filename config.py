from dataclasses import dataclass
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    provider: str
    model: str
    api_key: str
    yaml_path: str


def _load_env() -> None:
    load_dotenv()

def load_yaml_path() -> str:
    _load_env()
    yaml_path = os.environ.get("RRM_AI_YAML")
    if not yaml_path:
        raise ValueError("RRM_AI_YAML is required")
    return yaml_path


def load_config() -> Config:
    _load_env()

    api_key = os.environ.get("RRM_AI_API_KEY")
    if not api_key:
        raise ValueError("RRM_AI_API_KEY is required")
    yaml_path = os.environ.get("RRM_AI_YAML")
    if not yaml_path:
        raise ValueError("RRM_AI_YAML is required")

    return Config(
        provider=os.environ.get("RRM_AI_PROVIDER", "anthropic"),
        model=os.environ.get("RRM_AI_MODEL", "claude-sonnet-4-5-20250929"),
        api_key=api_key,
        yaml_path=yaml_path,
    )
