"""Shared SSH connection defaults for backend features."""
from __future__ import annotations

import os
from typing import Any


def ssh_connect_options(**kwargs: Any) -> dict[str, Any]:
    """Return AsyncSSH connect kwargs with local user config loading disabled.

    CMDB and task execution pass explicit host/user/password values. Letting
    AsyncSSH read ~/.ssh/config can fail under Windows service accounts or
    locked-down home directories before it ever tries the target host.
    """
    options: dict[str, Any] = {
        "config": None,
        "client_keys": None,
        "agent_path": None,
    }
    strict = os.getenv("SSH_STRICT_HOST_KEY_CHECKING", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
    known_hosts = os.getenv("SSH_KNOWN_HOSTS", "").strip()
    if not strict:
        options["known_hosts"] = None
    elif known_hosts:
        options["known_hosts"] = known_hosts
    options.update(kwargs)
    return options
