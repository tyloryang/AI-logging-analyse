"""Shared SSH connection defaults for backend features."""
from __future__ import annotations

from typing import Any


def ssh_connect_options(**kwargs: Any) -> dict[str, Any]:
    """Return AsyncSSH connect kwargs with local user config loading disabled.

    CMDB and task execution pass explicit host/user/password values. Letting
    AsyncSSH read ~/.ssh/config can fail under Windows service accounts or
    locked-down home directories before it ever tries the target host.
    """
    options: dict[str, Any] = {
        "known_hosts": None,
        "config": None,
        "client_keys": None,
        "agent_path": None,
    }
    options.update(kwargs)
    return options
