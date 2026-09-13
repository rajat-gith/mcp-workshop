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


if __name__ == "__main__":
    mcp.run()