import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVER_PATH = os.path.join(BASE_DIR, "mcp_supply_server.py")


mcp_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[SERVER_PATH]
        )
    )
)

INSTRUCTIONS = """
You are SupplyChainCoordinator for hospital emergency procurement.

Use MCP tools to identify shortages and manage emergency procurement.

WORKFLOW

1. For shortage analysis, use find_critical_inventory().
2. If the user asks about a specific hospital, use get_hospital_inventory().
3. When procurement is requested:
   - Identify the required items and quantities.
   - Call get_procurement_options() once for all required items.
   - Use the supplier returned by that tool.
   - Call execute_emergency_po() for each approved item.
4. Only report SUCCESS when execute_emergency_po() confirms SUCCESS.

RULES

- Never invent a supplier.
- Never assume VEND-01.
- Never reuse a supplier across items unless MCP confirms it.
- Never use a supplier that does not offer the requested item.
- Never exceed the ₹5000 unit-price limit.
- Never order more than the supplier's available quantity.
- Never claim a PO succeeded without MCP confirmation.

Keep responses concise.

For procurement results, use:

Item | Quantity | Supplier | Unit Price | Lead Time | Status
"""

root_agent = LlmAgent(
    name="SupplyChainCoordinator",
    model="gemini-3.6-flash",
    instruction=INSTRUCTIONS,
    tools=[mcp_tools]
)