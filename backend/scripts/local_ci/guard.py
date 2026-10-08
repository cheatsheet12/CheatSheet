"""Refuse to point the run at anything that is not a local, throwaway service.

The integration suite is destructive (it creates and truncates data), so a stray
`DATABASE_URL` pointing at staging must never reach a child process.
"""

from __future__ import annotations

from urllib.parse import urlsplit

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class NonLocalTargetError(ValueError):
    """A service URL points at a host that is not this machine."""


def host_of(url: str) -> str | None:
    try:
        return urlsplit(url).hostname
    except ValueError:
        return None


def assert_local(url: str, label: str) -> None:
    """Raise unless `url` names a loopback host. The URL itself is never echoed."""
    host = host_of(url)
    if host is None or host.lower() not in LOCAL_HOSTS:
        shown = host if host else "<unparseable>"
        raise NonLocalTargetError(
            f"{label} targets host '{shown}', which is not local. "
            "The local CI only runs against throwaway containers on localhost."
        )
