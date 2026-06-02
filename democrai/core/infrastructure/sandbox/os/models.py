from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkEndpoint:
    host: str
    port: int
    protocol: str = "tcp"
    source: str = ""
    purpose: str = ""


@dataclass(frozen=True)
class ApplicationNetworkAllowlist:
    endpoints: list[NetworkEndpoint]

