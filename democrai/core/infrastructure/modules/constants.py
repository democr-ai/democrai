import platform


CURRENT_PLATFORM = platform.system().lower()
CURRENT_ARCH = platform.machine().lower()
if CURRENT_ARCH in ["amd64", "x86_64"]:
    CURRENT_ARCH = "x86_64"
elif CURRENT_ARCH in ["arm64", "aarch64"]:
    CURRENT_ARCH = "arm64"

DEFAULT_LEASE_TTL_SECONDS = 30.0
SCHEDULE_POLL_SECONDS = 1.0
