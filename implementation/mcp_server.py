"""
FastMCP Server Module for SQLite Lab.
Exposes database tools (search, insert, aggregate) and resources (schemas) via FastMCP.
Supports standard I/O (stdio), HTTP, and SSE transports with optional Bearer Token authentication.
"""

import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from .db import DatabaseAdapter, ValidationError, get_adapter

# Initialize the FastMCP server
mcp = FastMCP("SQLite Lab MCP Server")

# Global adapter reference, initialized on import or CLI execution
_adapter: DatabaseAdapter | None = None


def get_db_adapter(db_url_or_path: str | Path | None = None) -> DatabaseAdapter:
    """Retrieve or initialize the singleton database adapter."""
    global _adapter
    if _adapter is None or db_url_or_path is not None:
        _adapter = get_adapter(db_url_or_path)
    return _adapter


@mcp.tool(name="search", description="Search and filter records from a database table with sorting and pagination.")
def search(
    table: str,
    filters: list[dict[str, Any]] | None = None,
    columns: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
) -> dict[str, Any]:
    """
    Search records in the specified table.

    Args:
        table: The name of the table to query (e.g., 'students', 'courses', 'enrollments').
        filters: List of filter dicts, each containing 'column', 'operator' (e.g. '=', '>', 'LIKE', 'IN'), and 'value'.
        columns: Optional list of column names to return. Defaults to all columns (*).
        limit: Maximum number of records to return (default 20, max 500).
        offset: Number of records to skip for pagination (default 0).
        order_by: Optional column name to sort by.
        descending: Whether to sort in descending order (default False).

    Returns:
        A structured JSON dictionary containing matching rows and pagination metadata.
    """
    adapter = get_db_adapter()
    try:
        return adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )
    except ValidationError as e:
        raise ValueError(f"Validation Error: {str(e)}")


@mcp.tool(name="insert", description="Insert a new record into a database table. Rejects empty payloads and validates schema.")
def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
    """
    Insert a record into the specified table.

    Args:
        table: Target table name.
        values: Dictionary mapping column names to values. Must not be empty.

    Returns:
        A dictionary containing status and the inserted record (including auto-generated IDs).
    """
    adapter = get_db_adapter()
    try:
        return adapter.insert(table=table, values=values)
    except ValidationError as e:
        raise ValueError(f"Validation Error: {str(e)}")


@mcp.tool(name="aggregate", description="Compute aggregate metrics (count, avg, sum, min, max) over a table.")
def aggregate(
    table: str,
    metric: str,
    column: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    group_by: str | None = None,
) -> dict[str, Any]:
    """
    Compute aggregate statistics on table data.

    Args:
        table: Target table name.
        metric: Aggregate function to apply: 'count', 'avg', 'sum', 'min', or 'max'.
        column: Target column for avg, sum, min, max. Optional for count.
        filters: Optional list of filter dicts to restrict the rows evaluated.
        group_by: Optional column name to group results by.

    Returns:
        A structured dictionary containing the computed metrics.
    """
    adapter = get_db_adapter()
    try:
        return adapter.aggregate(
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )
    except ValidationError as e:
        raise ValueError(f"Validation Error: {str(e)}")


@mcp.resource("schema://database", description="Full database schema snapshot including tables, columns, and foreign keys.")
def database_schema() -> str:
    """
    Inspect all tables in the database and return a formatted JSON string representing the full schema.
    """
    adapter = get_db_adapter()
    schema_data = adapter.get_full_schema()
    return json.dumps(schema_data, indent=2)


@mcp.resource("schema://table/{table_name}", description="Dynamic schema template for a single table.")
def table_schema(table_name: str) -> str:
    """
    Inspect a specific table and return its schema definition as a formatted JSON string.
    """
    adapter = get_db_adapter()
    try:
        schema_data = adapter.get_table_schema(table_name)
        return json.dumps(schema_data, indent=2)
    except ValidationError as e:
        raise ValueError(f"Validation Error: {str(e)}")


def parse_args():
    parser = argparse.ArgumentParser(description="Run the SQLite Lab FastMCP Server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport protocol to use (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind for HTTP/SSE transports (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port number to bind for HTTP/SSE transports (default: 8000)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database path or PostgreSQL URL (overrides default school.db and DATABASE_URL)",
    )
    parser.add_argument(
        "--auth-token",
        default=os.getenv("MCP_AUTH_TOKEN"),
        help="Bearer authentication token for HTTP/SSE transport (can also set MCP_AUTH_TOKEN env var)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    # Initialize adapter with custom db-url if provided
    if args.db_url:
        get_db_adapter(args.db_url)
    else:
        get_db_adapter()

    if args.auth_token and args.transport in ["http", "sse"]:
        print(f"[{args.transport.upper()} Mode] Authentication enabled. Requiring Bearer token.")

    print(f"Starting FastMCP Server using '{args.transport}' transport...")
    if args.transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=args.transport, host=args.host, port=args.port)
