# MCP Workshop — Setup & Code Reference
### Repo: `rajat-gith/mcp-workshop`

This guide walks through **what the project does**, **how to set it up and run it**, and breaks down every MCP tool and the agent code into separate, copyable blocks with a short explanation of each.

---

## 1. What this project is

A small **hospital supply-chain agent** built with:

- **Google ADK (Agent Development Kit)** — hosts an `LlmAgent` (using a Gemini model) that talks to a user.
- **MCP (Model Context Protocol)** — a local MCP server (`mcp_supply_server.py`) exposes 4 "tools" (Python functions) that the agent can call to read inventory data, check suppliers, and place emergency purchase orders.
- **CSV files** (`inventory.csv`, `suppliers.csv`) act as the "database" the tools read from.

Flow: **User → LlmAgent (Gemini) → MCP tool calls (stdio) → mcp_supply_server.py → CSV data → result back to agent → answer to user.**

---

## 2. Project structure

```
mcp-workshop/
├── inventory.csv                  # hospital stock data
├── suppliers.csv                  # supplier catalogue
├── mcp_supply_server.py           # MCP server exposing 4 tools
├── .gitignore
└── supply_chain_agent/
    ├── __init__.py                # exposes root_agent
    └── agent.py                   # defines the LlmAgent + connects to MCP server
```

---

## 3. Prerequisites

- **Python 3.10+**
- A **Google AI Studio API key** (Gemini) — the agent uses model `"gemini-3.6-flash"` via Google ADK, which needs `GOOGLE_API_KEY` (or Vertex AI credentials) set as an environment variable.
- Internet access is only needed for the LLM call — the MCP server itself runs 100% locally against the CSV files.

> Note: check the current Gemini model names available to your API key — `gemini-3.6-flash` may need to be swapped for whatever model string is currently valid on your account.

---

## 4. Step-by-step setup

### Step 1 — Clone the repo
```bash
git clone https://github.com/rajat-gith/mcp-workshop.git
cd mcp-workshop
```

### Step 2 — Create and activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
```

### Step 3 — Install dependencies
The repo has no `requirements.txt`, so install the two libraries it imports directly:
```bash
pip install google-adk mcp python-dotenv
```
- `google-adk` → provides `LlmAgent`, `McpToolset`, `StdioConnectionParams`
- `mcp` → provides `StdioServerParameters` and `FastMCP` (used to build the tool server)

### Step 4 — Set your Gemini API key
Create a `.env` file in the repo root (it's already git-ignored) or export it directly:
```bash
# .env file
GOOGLE_API_KEY=your_gemini_api_key_here
```
or
```bash
export GOOGLE_API_KEY=your_gemini_api_key_here
```

### Step 5 — (Optional) Sanity-check the MCP server on its own
This starts the raw MCP server over stdio so you can confirm it boots without errors:
```bash
python mcp_supply_server.py
```
It will just sit there listening on stdio (no output) — that's expected. `Ctrl+C` to stop; the agent will launch it automatically anyway.

### Step 6 — Run the agent with the ADK CLI
From the **repo root** (the folder that contains `supply_chain_agent/`):
```bash
adk run supply_chain_agent
```
or, for the browser-based dev UI:
```bash
adk web
```
Then pick `supply_chain_agent` from the dropdown in the browser UI. `adk` automatically:
1. Imports `root_agent` from `supply_chain_agent/__init__.py`
2. Spawns `mcp_supply_server.py` as a subprocess over stdio (this is what `McpToolset` + `StdioConnectionParams` do)
3. Lets the Gemini model call the 4 exposed tools during the conversation

### Step 7 — Try it out
Example prompts once the agent is running:
```
What items are critically low across all hospitals?
```
```
Show me the full inventory for HOSP-A.
```
```
Find suppliers and place emergency orders for the critical shortages at HOSP-A.
```

---

## 5. Data files reference

### `inventory.csv`
Per-hospital stock levels.

| column | meaning |
|---|---|
| `hospital_id` | e.g. `HOSP-A` |
| `hospital_name`, `location` | display info |
| `item`, `category` | e.g. `IV_Fluids`, `Critical Care` |
| `stock`, `threshold` | current stock vs. minimum safe level |
| `unit` | e.g. `bags`, `units`, `boxes` |
| `unit_price`, `supplier`, `lead_time_days` | reference info (not authoritative — the server re-checks live supplier data) |
| `criticality` | `HIGH` / `CRITICAL` / `MEDIUM` |

### `suppliers.csv`
Supplier catalogue, used for sourcing.

| column | meaning |
|---|---|
| `item` | item name (matched case-insensitively) |
| `supplier_id`, `supplier_name` | e.g. `VEND-01`, `MedSupply Co.` |
| `unit_price`, `lead_time_days` | used to rank suppliers |
| `available_quantity` | stock the supplier can fulfill |
| `availability` | `AVAILABLE` / otherwise excluded |

---

## 6. `mcp_supply_server.py` — broken down tool by tool

### 6.0 Server bootstrap
Sets up the FastMCP server instance and file paths. Every tool below is attached to this `mcp` object.

```python
import csv
import os
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Hospital-Supply-Hub")

BASE = os.path.dirname(os.path.abspath(__file__))
INV = os.path.join(BASE, "inventory.csv")
SUP = os.path.join(BASE, "suppliers.csv")


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
```
**What it does:** `FastMCP("Hospital-Supply-Hub")` creates the MCP server and names it. `load()` is a small helper that reads any CSV file into a list of dicts (one dict per row) using the header row as keys — every tool below reuses it instead of repeating file-reading code.

---

### 6.1 Tool: `get_hospital_inventory`
**Purpose:** Look up the complete stock list for one specific hospital by ID, and flag which items are below their safety threshold.

```python
@mcp.tool()
async def get_hospital_inventory(hospital_id: str) -> dict:
    """Get complete inventory for a hospital."""
    rows = [r for r in load(INV)
            if r["hospital_id"].upper() == hospital_id.upper()]

    if not rows:
        return {"error": f"Hospital {hospital_id} not found."}

    inventory = []
    for r in rows:
        stock, threshold = int(r["stock"]), int(r["threshold"])
        inventory.append({
            "item": r["item"],
            "category": r["category"],
            "stock": stock,
            "threshold": threshold,
            "unit": r["unit"],
            "status": "CRITICAL" if stock < threshold else "NORMAL",
            "shortage": max(0, threshold - stock),
            "criticality": r["criticality"]
        })

    return {
        "hospital_id": rows[0]["hospital_id"],
        "hospital_name": rows[0]["hospital_name"],
        "location": rows[0]["location"],
        "inventory": inventory
    }
```
**How it works:**
- `@mcp.tool()` registers this function as an MCP tool the LLM can call — the docstring (`"""Get complete inventory..."""`) becomes the tool's description shown to the model, so it knows when to use it.
- It filters `inventory.csv` rows matching the given `hospital_id` (case-insensitive).
- For each row, it computes a `status` (`CRITICAL` if `stock < threshold`) and a `shortage` amount.
- Returns a structured dict — MCP tools typically return JSON-serializable data (dict/str/etc.) so the model can reason over it directly.

---

### 6.2 Tool: `find_critical_inventory`
**Purpose:** Scan *all* hospitals and return every item currently below its safety threshold — used for a system-wide shortage report.

```python
@mcp.tool()
async def find_critical_inventory() -> dict:
    """Find all items below threshold."""
    critical = []

    for r in load(INV):
        stock, threshold = int(r["stock"]), int(r["threshold"])

        if stock < threshold:
            critical.append({
                "hospital_id": r["hospital_id"],
                "hospital_name": r["hospital_name"],
                "item": r["item"],
                "stock": stock,
                "threshold": threshold,
                "shortage": threshold - stock,
                "unit": r["unit"],
                "criticality": r["criticality"]
            })

    return {
        "critical_count": len(critical),
        "critical_inventory": critical
    }
```
**How it works:**
- Takes no arguments — it's a global scan across the entire inventory file.
- Same threshold logic as above, but not scoped to one hospital.
- Returns a count plus the list, which the agent's system prompt tells it to call first for any "shortage analysis" request.

---

### 6.3 Tool: `get_procurement_options`
**Purpose:** Given a list of needed items and quantities, find the best (fastest, valid) supplier for each — without actually placing any order yet.

```python
@mcp.tool()
def get_procurement_options(
    items: list[str],
    quantities: dict[str, int]
) -> dict:
    """Find the fastest valid supplier for multiple items."""
    suppliers = load(SUP)
    results = {}

    for item in items:
        qty = quantities.get(item, 0)

        matches = [
            s for s in suppliers
            if s["item"].lower() == item.lower()
            and int(s["available_quantity"]) >= qty
            and float(s["unit_price"]) <= 5000
            and s["availability"].upper() == "AVAILABLE"
        ]

        if not matches:
            results[item] = {
                "status": "NO_VALID_SUPPLIER",
                "quantity": qty
            }
            continue

        matches.sort(
            key=lambda s: (
                int(s["lead_time_days"]),
                float(s["unit_price"])
            )
        )

        s = matches[0]
        price = float(s["unit_price"])

        results[item] = {
            "status": "READY",
            "quantity": qty,
            "supplier_id": s["supplier_id"],
            "supplier_name": s["supplier_name"],
            "unit_price": price,
            "total_price": price * qty,
            "lead_time_days": int(s["lead_time_days"])
        }

    return results
```
**How it works:**
- Note this one is a **regular `def`, not `async def`** — MCP/FastMCP supports both sync and async tool functions.
- Takes `items` (list of item names) and `quantities` (dict mapping item → needed amount).
- For each item, filters suppliers where: the item matches, enough stock is available, the unit price is within the ₹5000 safety cap, and the supplier is marked `AVAILABLE`.
- Sorts valid suppliers by **lead time first, then price**, and picks the top one.
- If nothing qualifies, marks that item `NO_VALID_SUPPLIER` instead of guessing.

---

### 6.4 Tool: `execute_emergency_po`
**Purpose:** Actually create ("execute") a purchase order for one item from one supplier — with hard safety checks so the LLM can't be talked into a bad order.

```python
@mcp.tool()
async def execute_emergency_po(
    supplier_id: str,
    item: str,
    quantity: int,
    price: float
) -> str:
    """Create emergency PO with safety checks."""

    if price > 5000:
        return f"BLOCKED: Unit price {price} exceeds ₹5000 cap."

    if quantity <= 0:
        return "BLOCKED: Quantity must be greater than zero."

    for s in load(SUP):
        if (
            s["supplier_id"] == supplier_id
            and s["item"].lower() == item.lower()
        ):
            available = int(s["available_quantity"])

            if quantity > available:
                return (
                    f"BLOCKED: Only {available} units of "
                    f"{item} available."
                )

            total = quantity * price

            return (
                f"SUCCESS: Emergency PO generated. "
                f"Supplier={supplier_id}, Item={item}, "
                f"Quantity={quantity}, Unit Price={price}, "
                f"Total={total}, Status=APPROVED"
            )

    return "BLOCKED: Supplier does not offer this item."
```
**How it works:**
- Validates price cap (₹5000/unit) and quantity (> 0) **before** touching supplier data — fail fast on obviously bad input.
- Looks up the specific `supplier_id` + `item` combo in `suppliers.csv`.
- Checks the requested `quantity` doesn't exceed what that supplier actually has.
- On success, returns a plain string confirming the order — this is the *only* function that can produce a "SUCCESS" result, which is why `agent.py`'s instructions say never to claim success without this tool confirming it.

---

### 6.5 Server entry point

```python
if __name__ == "__main__":
    mcp.run()
```
**What it does:** Starts the MCP server over stdio when the file is run directly. `mcp.run()` is what makes this script speak the MCP protocol so a client (like the ADK agent below) can connect to it as a subprocess.

---

## 7. `supply_chain_agent/agent.py` — broken down

### 7.1 Imports & path setup
```python
import os
import sys

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from mcp import StdioServerParameters


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SERVER_PATH = os.path.join(BASE_DIR, "mcp_supply_server.py")
```
**What it does:** Computes the absolute path to `mcp_supply_server.py`, which lives one directory *up* from `agent.py` (in the repo root), so the agent can launch it regardless of the current working directory.

### 7.2 Connecting the agent to the MCP server
```python
mcp_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command=sys.executable,
            args=[SERVER_PATH]
        )
    )
)
```
**What it does:** `McpToolset` is Google ADK's bridge to an MCP server. `StdioConnectionParams` tells it to launch the server as a **local subprocess** (`command=sys.executable` = the same Python interpreter currently running, `args=[SERVER_PATH]` = run `mcp_supply_server.py`) and talk to it over stdin/stdout. Once connected, all 4 tools defined in the server become available to the agent automatically — no manual tool registration needed on the agent side.

### 7.3 System instructions
```python
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
```
**What it does:** This is the system prompt that constrains the LLM's behavior. It explicitly maps user intents to which tool to call and in what order, and repeats the same safety rules that are hard-coded into `execute_emergency_po` — a form of defense in depth (the LLM is told the rules, and the server also enforces them regardless).

### 7.4 Defining the agent
```python
root_agent = LlmAgent(
    name="SupplyChainCoordinator",
    model="gemini-3.6-flash",
    instruction=INSTRUCTIONS,
    tools=[mcp_tools]
)
```
**What it does:** Creates the actual ADK agent object: gives it a name, picks the underlying Gemini model, attaches the system instructions, and hands it the `mcp_tools` toolset so it can call the 4 MCP tools during a conversation. `root_agent` is the name ADK's CLI (`adk run` / `adk web`) looks for by convention.

### 7.5 `supply_chain_agent/__init__.py`
```python
from .agent import root_agent
```
**What it does:** Re-exports `root_agent` at the package level so `adk run supply_chain_agent` can find it just by importing the package name.

---

## 8. Quick troubleshooting

| Symptom | Likely cause |
|---|---|
| `ModuleNotFoundError: google.adk` | `pip install google-adk` wasn't run in the active venv |
| `ModuleNotFoundError: mcp` | `pip install mcp` missing |
| Agent never calls tools / errors on connect | `mcp_supply_server.py` path wrong, or it isn't executable via `sys.executable` — try running it manually first (Step 5) |
| Auth / model errors from Gemini | `GOOGLE_API_KEY` not set, invalid, or the model string `gemini-3.6-flash` isn't available on your account — check current valid model names |
| `BLOCKED` responses on every order | Working as intended — check the ₹5000 price cap and `available_quantity` in `suppliers.csv` |