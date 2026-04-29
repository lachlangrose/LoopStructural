"""Standalone MCP server runner for LoopStructural.

This module can be used to run the LoopStructural MCP server as a standalone
process that agents can communicate with via JSON-RPC over stdio.

Usage:
    python -m loop_mcp_server.run_server
"""

import asyncio
import json
import logging
import sys
from typing import Any

from loop_mcp_server import LoopStructuralMCPServer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


class MCPStdioServer:
    """MCP server that communicates via JSON-RPC over stdio."""

    def __init__(self, validation_mode: str = "strict"):
        """Initialize the stdio server."""
        self.server = LoopStructuralMCPServer(validation_mode=validation_mode)
        self.message_id = 0

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Handle a JSON-RPC request.

        Args:
            request: JSON-RPC request dictionary

        Returns:
            JSON-RPC response
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                response = self._handle_initialize()
            elif method == "list_tools":
                response = self._handle_list_tools()
            elif method == "call_tool":
                response = await self._handle_call_tool(
                    params.get("name"), params.get("arguments", {})
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": response,
            }
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(e)},
            }

    def _handle_initialize(self) -> dict[str, Any]:
        """Handle initialization request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
            },
            "serverInfo": {
                "name": "LoopStructural MCP Server",
                "version": "0.1.0",
            },
        }

    def _handle_list_tools(self) -> dict[str, Any]:
        """Handle list_tools request."""
        tools = self.server.get_tools()
        tools_list = [
            {
                "name": name,
                "description": tool["description"],
                "inputSchema": tool["inputSchema"],
            }
            for name, tool in tools.items()
        ]
        return {"tools": tools_list}

    async def _handle_call_tool(
        self, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Handle call_tool request."""
        if tool_name not in self.server.tools:
            raise ValueError(f"Tool '{tool_name}' not found")

        result = await self.server.call_tool(tool_name, arguments)
        return {"content": [{"type": "text", "text": result}]}

    async def run(self) -> None:
        """Run the server, reading requests from stdin and writing responses to stdout."""
        logger.info("LoopStructural MCP Server started")

        try:
            while True:
                # Read a line from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)
                    print(json.dumps(response))
                    sys.stdout.flush()
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {e}")
                    error_response = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                    }
                    print(json.dumps(error_response))
                    sys.stdout.flush()
        except KeyboardInterrupt:
            logger.info("Server interrupted")
        except Exception as e:
            logger.error(f"Fatal error: {e}")
            sys.exit(1)


async def main():
    """Main entry point."""
    server = MCPStdioServer(validation_mode="strict")
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
