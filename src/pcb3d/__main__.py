"""Allow ``python -m pcb3d`` to behave like the installed CLI."""

from .cli import main

raise SystemExit(main())
