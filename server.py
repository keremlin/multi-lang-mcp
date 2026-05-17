import argparse
import logging

from mcp.server.fastmcp import FastMCP

from shared.logging_config import setup_logging
from shared.powershell_runner import run_powershell
from shared.python_runner import run_python
from shared.node_runner import run_node
from shared.java_runner import run_java

setup_logging()
logger = logging.getLogger(__name__)

mcp = FastMCP("multi-lang-mcp")


@mcp.tool()
def windows_services(filter_name: str = "") -> dict:
    """List Windows services, optionally filtered by name."""
    args = [filter_name] if filter_name else []
    return run_powershell("tools/powershell/services.ps1", args)


@mcp.tool()
def read_file(path: str) -> dict:
    """Read a file from disk and return its contents."""
    return run_python("tools/python/read_file.py", [path])


@mcp.tool()
def npm_package_info(package_name: str) -> dict:
    """Fetch metadata about an npm package."""
    return run_node("tools/node/npm_info.js", [package_name])


@mcp.tool()
def java_tool(input_json: str = "{}") -> dict:
    """Run the Java ToolRunner with optional JSON input."""
    return run_java("tools/java/build/ToolRunner.jar", stdin_data=input_json)


@mcp.tool()
def download_file(url: str, save_path: str) -> dict:
    """Download a file from a URL and save it to disk. Returns progress milestones and final percentage."""
    return run_python("tools/python/download_file.py", [url, save_path], timeout=300)


@mcp.tool()
def youtube_download(url: str, retries: int = 3, timeout: int = 30, video_format: str = "bestvideo+bestaudio/best") -> dict:
    """Download a YouTube video to the user's Downloads folder.

    Args:
        url: Full YouTube video URL (watch?v=... or playlist link).
        retries: Number of download retries on transient errors (default 3).
        timeout: Socket timeout in seconds for each network operation (default 30).
        video_format: yt-dlp format string, e.g. 'best[ext=mp4]' or 'bestvideo+bestaudio/best' (default).
    """
    return run_python(
        "tools/python/youtube_download.py",
        [url, str(retries), str(timeout), video_format],
        timeout=600,
    )


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Multi-language MCP server")
    p.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport type (default: stdio; use sse/streamable-http for service mode)",
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind host for SSE/HTTP (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8080, help="Bind port for SSE/HTTP (default: 8080)")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    mcp.settings.host = args.host
    mcp.settings.port = args.port
    logger.info("MCP server starting (transport=%s, host=%s, port=%s)", args.transport, args.host, args.port)
    mcp.run(transport=args.transport)
