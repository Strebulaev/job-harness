"""Currency and period normalization to USD/month (spec §10).

Uses the static FX-rate table from config (``fx.rates``, keyed by ISO-4217
currency code) with the ``fx.fx_as_of`` date. Hourly rates are converted via
``hours_per_week`` (weekly x 52 / 12) or the 120 h/month default, which drops
confidence to ``low``.

The output ``NormalizedCompensation`` carries the USD/month band plus the
confidence label (``high`` / ``low``) that the router's rate-fit scoring and
the ``comp_confidence`` column on ``jobs`` consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jobharness.schemas.jd import Compensation
from jobharness.settings import Settings

HOURS_MONTH_DEFAULT = 120.0
WEEKS_PER_YEAR = 52.0


class UnknownCurrencyError(ValueError):
    """Raised when a currency is not present in the config FX table."""

    def __init__(self, currency: str) -> None:
        self.currency = currency
        super().__init__(
            f"currency {currency!r} not in fx.rates (fx_as_of={_FX_AS_OF})"
        )


# Set by :func:`normalize_compensation` from settings on each call so the
# module stays stateless; the error message above references the last-used
# as-of date.
_FX_AS_OF: str = "n/a"


@dataclass(slots=True)
class NormalizedCompensation:
    """USD/month band plus provenance metadata."""

    usd_min_month: float
    usd_max_month: float
    confidence: str  # "high" | "low"
    currency: str
    period: str
    source_comp: dict[str, object] = field(default_factory=dict)


def _rate_for(settings: Settings, currency: str) -> float:
    rates = settings.fx.rates.model_dump()
    code = currency.strip().upper()
    if code not in rates:
        raise UnknownCurrencyError(code)
    value: float = float(rates[code])
    return value


def _to_usd(amount: float, currency: str, rate: float) -> float:
    code = currency.strip().upper()
    if code == "USD":
        return amount
    return amount * rate


def normalize_compensation(
    comp: Compensation,
    settings: Settings,
    hours_per_week: tuple[float, float] | None = None,
) -> NormalizedCompensation:
    """Convert a raw :class:`Compensation` to USD/month.

    - ``month`` -> direct FX conversion, confidence ``high``.
    - ``year``  -> FX conversion, divide by 12, confidence ``high``.
    - ``hour``  -> FX conversion, multiply by ``hours_per_week`` (weekly mean
      x 52/12) when available, else 120 h/month; confidence ``low`` either way
      (hourly bands are wide and hours vary).
    - ``project`` -> not convertible to a monthly band without a duration;
      returns confidence ``low`` with the raw band passed through unchanged,
      flagging the router to treat the comp as ``ask_rate``.
    """
    global _FX_AS_OF
    _FX_AS_OF = settings.fx.fx_as_of
    rate = _rate_for(settings, comp.currency)
    lo_usd = _to_usd(comp.min, comp.currency, rate)
    hi_usd = _to_usd(comp.max, comp.currency, rate)

    if comp.period == "month":
        return NormalizedCompensation(
            usd_min_month=lo_usd,
            usd_max_month=hi_usd,
            confidence="high",
            currency=comp.currency.upper(),
            period="month",
            source_comp=comp.model_dump(),
        )

    if comp.period == "year":
        return NormalizedCompensation(
            usd_min_month=lo_usd / 12.0,
            usd_max_month=hi_usd / 12.0,
            confidence="high",
            currency=comp.currency.upper(),
            period="year",
            source_comp=comp.model_dump(),
        )

    if comp.period == "hour":
        if hours_per_week is not None:
            hours_month = ((hours_per_week[0] + hours_per_week[1]) / 2.0) * WEEKS_PER_YEAR / 12.0
        else:
            hours_month = HOURS_MONTH_DEFAULT
        return NormalizedCompensation(
            usd_min_month=lo_usd * hours_month,
            usd_max_month=hi_usd * hours_month,
            confidence="low",
            currency=comp.currency.upper(),
            period="hour",
            source_comp=comp.model_dump(),
        )

    # project: not monthly-convertible without a stated duration.
    return NormalizedCompensation(
        usd_min_month=lo_usd,
        usd_max_month=hi_usd,
        confidence="low",
        currency=comp.currency.upper(),
        period="project",
        source_comp=comp.model_dump(),
    )


__all__ = [
    "HOURS_MONTH_DEFAULT",
    "NormalizedCompensation",
    "UnknownCurrencyError",
    "normalize_compensation",
]
