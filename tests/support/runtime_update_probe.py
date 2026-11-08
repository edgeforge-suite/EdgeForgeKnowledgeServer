"""Child-process probe for FastMCP startup update-check isolation."""

from __future__ import annotations

import os

import fastmcp
from fastmcp.utilities import version_check

from knowledge_server.server import mcp


def _fail_update_request(*args: object, **kwargs: object) -> None:
    raise AssertionError("FastMCP update-check HTTP path was invoked")


for include_prereleases in (False, True):
    cache_path = version_check._get_cache_path(include_prereleases)
    cache_path.unlink(missing_ok=True)

version_check.httpx.get = _fail_update_request
# server.main() is the production source of truth for update-check and stdio
# controls; this probe varies only the banner to prove the update guard is independent.
fastmcp.settings.check_for_updates = "off"
mcp.run(
    transport="stdio",
    show_banner=os.environ["KS_TEST_SHOW_BANNER"] == "1",
)
