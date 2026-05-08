#!/usr/bin/env python
"""Django management entrypoint."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Não foi possível importar Django. Garanta que o ambiente virtual "
            "está ativo (uv sync && .venv\\Scripts\\activate ou use uv run)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
