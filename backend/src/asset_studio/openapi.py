"""Write the API's OpenAPI document, the source of the generated frontend client (ADR-003).

    uv run python -m asset_studio.openapi ../frontend/src/api/openapi.json

A test checks that the committed copy matches the code, so the client cannot drift.
"""

import json
import sys
from pathlib import Path
from typing import Any


def document() -> dict[str, Any]:
    from asset_studio.main import create_app

    return create_app().openapi()


def render() -> str:
    return json.dumps(document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> None:
    text = render()
    if len(argv) > 1:
        Path(argv[1]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main(sys.argv)
