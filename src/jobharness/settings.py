"""Top-level configuration, validated by Pydantic. Unknown keys are errors."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PathsConfig(_Strict):
    data_dir: str = "./data"
    output_dir: str = "./data/out"


class LLMModels(_Strict):
    parse: str
    compose: str
    judge: str
    classify: str


class LLMTemperatures(_Strict):
    parse: float = Field(ge=0.0, le=2.0)
    compose: float = Field(ge=0.0, le=2.0)
    judge: float = Field(ge=0.0, le=2.0)
    classify: float = Field(ge=0.0, le=2.0)


class LLMConfig(_Strict):
    provider: Literal["anthropic", "fake"] = "anthropic"
    models: LLMModels
    temperature: LLMTemperatures
    max_retries: int = Field(default=3, ge=0)
    daily_token_budget: int = Field(default=2_000_000, gt=0)
    redact_pii_in_logs: bool = True


class WorkWindow(_Strict):
    start: str
    end: str


class PrincipalConfig(_Strict):
    timezone: str
    work_window_local: WorkWindow
    min_overlap_hours: float = Field(gt=0)
    target_overlap_hours: float = Field(gt=0)


class AutosendConfig(_Strict):
    enabled: bool = False
    allowed_channels: list[str] = Field(default_factory=list)


class RouterWeights(_Strict):
    """Score component weights (spec §11.3, section 5: 'weights in config')."""

    stack_match: float = 30.0
    rate_fit: float = 20.0
    tz_overlap: float = 15.0
    engagement_fit: float = 10.0
    scope_hours_fit: float = 10.0
    quality: float = 10.0


class RouterConfig(_Strict):
    min_score_to_apply: int = Field(ge=0, le=100)
    rate_floor_usd_month: float
    rate_ceiling_usd_month: float
    allow_below_floor_if_hours_leq: float | None = None
    countries_allow: list[str] = Field(default_factory=list)
    countries_deny: list[str] = Field(default_factory=list)
    engagement_types_allow: list[str] = Field(default_factory=list)
    weights: RouterWeights = Field(default_factory=RouterWeights)


class SendConfig(_Strict):
    autosend: AutosendConfig
    max_per_day: int = Field(gt=0)
    min_gap_seconds: int = Field(ge=0)
    quiet_hours_local: WorkWindow


class FollowupsConfig(_Strict):
    schedule_business_days: list[int] = Field(default_factory=list)
    max_followups: int = Field(ge=0)


class CapacityConfig(_Strict):
    max_total_hours_week: float = Field(gt=0)
    max_active_contracts: int = Field(ge=0)
    warn_at_utilization: float = Field(ge=0.0, le=1.0)


class FXRates(_Strict):
    model_config = ConfigDict(extra="allow")
    EUR: float = 1.0


class FXConfig(_Strict):
    fx_as_of: str
    rates: FXRates


class IngestConfig(_Strict):
    """Config for ingest adapters (spec §11.1)."""

    rss_feeds: list[str] = Field(default_factory=list)
    user_agent: str = "jobharness/0.1"
    email_alerts_imap: str | None = None
    email_alerts_label: str | None = None


class Settings(_Strict):
    paths: PathsConfig
    llm: LLMConfig
    principal: PrincipalConfig
    router: RouterConfig
    send: SendConfig
    followups: FollowupsConfig
    capacity: CapacityConfig
    fx: FXConfig
    ingest: IngestConfig | None = None

    @model_validator(mode="after")
    def _check_rates(self) -> Settings:
        if self.router.rate_floor_usd_month > self.router.rate_ceiling_usd_month:
            raise ValueError(
                "router.rate_floor_usd_month must be <= rate_ceiling_usd_month"
            )
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> Settings:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"config file not found: {p}")
        with p.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError("config root must be a mapping")
        return cls.model_validate(raw)

    def data_path(self) -> Path:
        return Path(self.paths.data_dir)

    def output_path(self) -> Path:
        return Path(self.paths.output_dir)
