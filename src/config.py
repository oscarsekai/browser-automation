from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import os


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def _parse_int(value: Optional[str], default: int) -> int:
    try:
        return int(str(value).strip()) if value is not None and str(value).strip() else default
    except ValueError:
        return default


def _parse_optional_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    stripped = str(value).strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _parse_float(value: Optional[str], default: float) -> float:
    try:
        return float(str(value).strip()) if value is not None and str(value).strip() else default
    except ValueError:
        return default


def _parse_csv(value: Optional[str]) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(',') if item.strip())


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[len('export '):]
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key] = value
    return result


@dataclass(frozen=True)
class Settings:
    scroll_count: int = 80
    scroll_pause_seconds: float = 1.5
    summary_top_n: int = 50
    summary_sentence_count: int = 5
    raw_retention_days: int = 3
    source_weight_a: float = 1.5
    source_weight_b: float = 1.0
    source_weight_c: float = 0.6
    freshness_weight: float = 0.20
    relevance_weight: float = 0.20
    density_weight: float = 0.15
    originality_weight: float = 0.10
    engagement_weight: float = 0.05
    duplicate_penalty: float = 0.25
    output_dir: str = 'data/summaries'
    raw_dir: str = 'data/raw'
    x_home_url: str = 'https://x.com/'
    focus_keywords: tuple[str, ...] = ()
    delete_raw_after_summary: bool = False
    cdp_remote_debugging_host: str = 'localhost'
    cdp_remote_debugging_port: Optional[int] = None
    cdp_target_url: str = 'about:blank'
    cdp_ws_url: Optional[str] = None
    openai_api_key: Optional[str] = None
    openai_base_url: str = 'https://api.openai.com/v1'
    summarize_model: str = 'gpt-4o-mini'


def load_settings(base_dir: Optional[Path] = None, environ: Optional[dict[str, str]] = None) -> Settings:
    base_dir = base_dir or Path.cwd()
    environ = dict(os.environ if environ is None else environ)
    file_values = load_env_file(base_dir / '.env.local')
    merged = {**file_values, **environ}
    return Settings(
        scroll_count=_parse_int(merged.get('SCROLL_COUNT'), 80),
        scroll_pause_seconds=_parse_float(merged.get('SCROLL_PAUSE_SECONDS'), 1.5),
        summary_top_n=_parse_int(merged.get('SUMMARY_TOP_N'), 50),
        summary_sentence_count=_parse_int(merged.get('SUMMARY_SENTENCE_COUNT'), 5),
        raw_retention_days=_parse_int(merged.get('RAW_RETENTION_DAYS'), 3),
        source_weight_a=_parse_float(merged.get('SOURCE_WEIGHT_A'), 1.5),
        source_weight_b=_parse_float(merged.get('SOURCE_WEIGHT_B'), 1.0),
        source_weight_c=_parse_float(merged.get('SOURCE_WEIGHT_C'), 0.6),
        freshness_weight=_parse_float(merged.get('FRESHNESS_WEIGHT'), 0.20),
        relevance_weight=_parse_float(merged.get('RELEVANCE_WEIGHT'), 0.20),
        density_weight=_parse_float(merged.get('DENSITY_WEIGHT'), 0.15),
        originality_weight=_parse_float(merged.get('ORIGINALITY_WEIGHT'), 0.10),
        engagement_weight=_parse_float(merged.get('ENGAGEMENT_WEIGHT'), 0.05),
        duplicate_penalty=_parse_float(merged.get('DUPLICATE_PENALTY'), 0.25),
        output_dir=merged.get('OUTPUT_DIR', 'data/summaries'),
        raw_dir=merged.get('RAW_DIR', 'data/raw'),
        x_home_url=merged.get('X_HOME_URL', 'https://x.com/'),
        focus_keywords=_parse_csv(merged.get('FOCUS_KEYWORDS')),
        delete_raw_after_summary=_parse_bool(merged.get('DELETE_RAW_AFTER_SUMMARY'), False),
        cdp_remote_debugging_host=merged.get('CDP_REMOTE_DEBUGGING_HOST', 'localhost'),
        cdp_remote_debugging_port=_parse_optional_int(merged.get('CDP_REMOTE_DEBUGGING_PORT')),
        cdp_target_url=merged.get('CDP_TARGET_URL', 'about:blank'),
        cdp_ws_url=merged.get('CDP_WS_URL') or None,
        openai_api_key=merged.get('OPENAI_API_KEY') or None,
        openai_base_url=merged.get('OPENAI_BASE_URL', 'https://api.openai.com/v1'),
        summarize_model=merged.get('SUMMARIZE_MODEL', 'gpt-4o-mini'),
    )
