"""MCP argument strictness (found by the interface sweep): unknown arguments are errors on MCP as on the CLI, and every
tool's advertised schema says so."""
import asyncio
import tempfile
import unittest

from openkatana.agent_api import TOOLS


class McpArgumentTests(unittest.TestCase):
    def test_unknown_arguments_rejected_and_schema_closed(self):
        from openkatana.mcp_server import create_server
        with tempfile.TemporaryDirectory() as ws:
            server = create_server(ws)
            tools = asyncio.run(server.list_tools())
            self.assertEqual(sorted(t.name for t in tools), sorted(TOOLS))
            self.assertTrue(all(t.inputSchema.get('additionalProperties') is False for t in tools))
            with self.assertRaisesRegex(Exception, '__bogus__|xtra'):
                asyncio.run(server.call_tool('list_sfx', {'__bogus__': 1}))
            ok = asyncio.run(server.call_tool('list_sfx', {'category': 'impact'}))
            self.assertTrue(ok)


if __name__ == '__main__':
    unittest.main()
