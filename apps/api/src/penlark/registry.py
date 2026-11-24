"""One registry of every adapter with its tier. Demo mode can only build the offline adapters."""

from __future__ import annotations

from penlark.adapters.schedulers import Buffer, FileExport, Metricool, Postiz, SeedScheduler
from sendora_core.adapters import AdapterError, AdapterRegistry, AdapterSpec

CATEGORIES = ("scheduler",)
ENV_VARS = {("scheduler", "postiz"): ["POSTIZ_API_KEY"], ("scheduler", "buffer"): ["BUFFER_TOKEN"], ("scheduler", "metricool"): ["METRICOOL_TOKEN", "METRICOOL_USER_ID", "METRICOOL_BLOG_ID"]}


def build_registry(settings) -> AdapterRegistry:
    reg = AdapterRegistry(settings)
    add = lambda c, n, t, f, notes="": reg.register(AdapterSpec(c, n, t, f, False, notes))  # noqa: E731
    add("scheduler", "seed", "A", SeedScheduler, "Offline demo. Keeps the draft in the app.")
    add("scheduler", "export", "A", FileExport, "The default. Saves the text to a file you copy from. Never sends.")
    add("scheduler", "postiz", "B", Postiz, "Request shape read from the Postiz docs on 2026-11-23. Tested against a local imitation only. Self hosted or cloud.")
    add("scheduler", "buffer", "B", Buffer, "createPost mutation read from the Buffer developer docs on 2026-11-23. Saves a draft by default. Tested against a local imitation only.")
    add("scheduler", "metricool", "B", Metricool, "Request shape from memory, UNVERIFIED. Tested against a local imitation only. API access may need a paid plan.")
    return reg


def build_scheduler(settings, registry=None):
    reg = registry or build_registry(settings)
    name = settings.scheduler_adapter
    if settings.demo_mode and name not in {"seed", "export"}:
        raise AdapterError("DEMO_MODE is on, so only offline adapters can be used. Change SCHEDULER_ADAPTER or turn DEMO_MODE off.")
    return reg.get("scheduler", name)
