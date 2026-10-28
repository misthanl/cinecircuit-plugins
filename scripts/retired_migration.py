"""Retired migration entry point; use the host deployment workflow.

Importing this module does not load credentials or connect to a NAS.
The old migration targeted a retired layout and must not run on current data.
"""

from pathlib import Path


def main(package=None, *, catalog=False):
    host = Path(__file__).resolve().parents[2] / "cinecircuit"
    entrypoint = host / ".planning/2026-07-19-phase91-nas-deploy/activate_current_release.py"
    raise RuntimeError(
        "Legacy plugin migration is retired. Build the reviewed release and use "
        f"{entrypoint} to activate it with backups and installed-plugin state preservation."
    )


if __name__ == "__main__":
    main()
