from __future__ import annotations

import warnings


def load_nvml():
    """Load NVML bindings while suppressing the deprecated pynvml import warning."""
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The pynvml package is deprecated.*",
                category=FutureWarning,
            )
            import pynvml as bindings  # type: ignore

        return bindings
    except ImportError:
        return None


nvml = load_nvml()


def has_nvml() -> bool:
    return nvml is not None
