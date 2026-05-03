"""Hosaka-native secrets store.

Two surfaces:

* :mod:`hosaka.secrets.store` — read/write the JSON store at
  ``~/.hosaka/secrets.json`` and mirror it into ``/etc/hosaka/env`` so
  systemd-launched daemons inherit the same values.
* :mod:`hosaka.secrets.cli` — ``python -m hosaka.secrets <verb>`` used
  by the bash ``hosaka secrets`` wrapper.

Source-of-truth flow::

    hosaka secrets set NAME=value      \\
        |                              \\
        v                              \\
    ~/.hosaka/secrets.json (chmod 600) \\
        |                              \\
        +--mirror---> /etc/hosaka/env (chmod 640) -> systemd EnvironmentFile

Every entrypoint (``python -m hosaka``, voice daemon, web server) calls
:func:`hosaka.secrets.store.apply_to_env` on import so the JSON store
also hydrates ``os.environ`` for in-process readers.
"""

from hosaka.secrets.store import apply_to_env, get, load, save, set as set_secret, unset

__all__ = ["apply_to_env", "get", "load", "save", "set_secret", "unset"]
