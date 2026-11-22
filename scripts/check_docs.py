"""Documentation checks for CI: wikilinks resolve and pages carry the required frontmatter."""

import pathlib
import re
import sys

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
REQUIRED = ("title:", "type:", "status:", "created:", "updated:")


def main() -> int:
    pages = list(DOCS.rglob("*.md"))
    names = {p.stem for p in pages}
    errors: list[str] = []
    for page in pages:
        text = page.read_text(encoding="utf-8")
        head = text.split("---", 2)[1] if text.startswith("---") else ""
        errors += [f"{page}: missing frontmatter {key}" for key in REQUIRED if key not in head]
        for link in re.findall(r"\[\[([^\]|#]+)", text):
            if link not in names:
                errors.append(f"{page}: broken wikilink [[{link}]]")
    print("\n".join(errors) or f"docs ok: {len(pages)} pages")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
