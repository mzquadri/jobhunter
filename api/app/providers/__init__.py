"""Provider registry.

Adding a source is: write the class, register it here, reference its name in
``config/profile.yml``. Nothing else in the system needs to know it exists.
"""

from __future__ import annotations

from app.providers.ats import (
    AshbyProvider,
    GreenhouseProvider,
    LeverProvider,
    PersonioProvider,
    SmartRecruitersProvider,
    SuccessFactorsProvider,
    WorkableProvider,
)
from app.providers.base import (
    FetchContext,
    Http,
    Provider,
    ProviderResult,
    RateLimited,
    run_provider,
)
from app.providers.boards import AdzunaProvider, ArbeitnowProvider, JobsChProvider
from app.providers.workday import WorkdayProvider

_ALL: list[type[Provider]] = [
    WorkdayProvider,
    SmartRecruitersProvider,
    SuccessFactorsProvider,
    GreenhouseProvider,
    LeverProvider,
    AshbyProvider,
    PersonioProvider,
    WorkableProvider,
    ArbeitnowProvider,
    JobsChProvider,
    AdzunaProvider,
]

REGISTRY: dict[str, Provider] = {cls.name: cls() for cls in _ALL}

EMPLOYER_PROVIDERS = frozenset(
    name for name, provider in REGISTRY.items() if provider.employer_scoped
)
BOARD_PROVIDERS = frozenset(REGISTRY) - EMPLOYER_PROVIDERS


def get_provider(name: str) -> Provider | None:
    return REGISTRY.get(name)


__all__ = [
    "BOARD_PROVIDERS",
    "EMPLOYER_PROVIDERS",
    "REGISTRY",
    "FetchContext",
    "Http",
    "Provider",
    "ProviderResult",
    "RateLimited",
    "get_provider",
    "run_provider",
]
