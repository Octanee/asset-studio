"""Run the MCP server: ``python -m asset_studio_mcp``."""

import uvicorn

from asset_studio_mcp.app import BIND, PORT, create_app


def main() -> None:
    uvicorn.run(create_app(), host=BIND, port=PORT, log_level="info")


if __name__ == "__main__":
    main()
