"""
Database Layer Module.
Provides validation, abstract interface for database adapters, and SQLite / PostgreSQL implementations.
"""

import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from .init_db import DEFAULT_DB_PATH, create_database

ALLOWED_OPERATORS = {"=", "!=", ">", "<", ">=", "<=", "LIKE", "IN", "NOT IN"}
ALLOWED_METRICS = {"count", "avg", "sum", "min", "max"}
MAX_LIMIT = 500  # Safety limit to prevent output token overflow


class ValidationError(ValueError):
    """Raised when a request cannot be safely executed."""
    pass


class DatabaseAdapter(ABC):
    """
    Abstract interface for Database Adapters.
    Supports both SQLite and PostgreSQL behind a shared interface.
    """

    @abstractmethod
    def connect(self) -> Any:
        """Open and return a database connection."""
        pass

    @abstractmethod
    def list_tables(self) -> list[str]:
        """Return a list of user table names in the database."""
        pass

    @abstractmethod
    def get_table_schema(self, table: str) -> dict[str, Any]:
        """Return schema information for a specific table."""
        pass

    @abstractmethod
    def get_full_schema(self) -> dict[str, Any]:
        """Return schema information for all tables in the database."""
        pass

    @abstractmethod
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Execute a safe, parameterized search query with filtering, sorting, and pagination."""
        pass

    @abstractmethod
    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        """Execute a safe, parameterized insert query and return the inserted payload."""
        pass

    @abstractmethod
    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        """Execute an aggregate calculation (count, avg, sum, min, max)."""
        pass


class SQLiteAdapter(DatabaseAdapter):
    """
    SQLite implementation of the DatabaseAdapter interface.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if not self.db_path.exists():
            create_database(self.db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def _validate_table(self, table: str, valid_tables: list[str] | None = None) -> None:
        if not table or not isinstance(table, str):
            raise ValidationError("Table name must be a non-empty string.")
        if valid_tables is None:
            valid_tables = self.list_tables()
        if table not in valid_tables:
            raise ValidationError(f"Unknown table '{table}'. Available tables: {valid_tables}")

    def _get_columns_for_table(self, table: str) -> list[str]:
        schema = self.get_table_schema(table)
        return [col["name"] for col in schema.get("columns", [])]

    def _validate_columns(self, table: str, columns: list[str], valid_columns: list[str] | None = None) -> None:
        if valid_columns is None:
            valid_columns = self._get_columns_for_table(table)
        for col in columns:
            if col not in valid_columns:
                raise ValidationError(f"Unknown column '{col}' in table '{table}'. Available columns: {valid_columns}")

    def _build_where_clause(self, table: str, filters: list[dict[str, Any]] | None, valid_columns: list[str]) -> tuple[str, list[Any]]:
        if not filters:
            return "", []

        if not isinstance(filters, list):
            raise ValidationError("Filters must be a list of filter dictionaries.")

        clauses = []
        params = []

        for f in filters:
            if not isinstance(f, dict):
                raise ValidationError("Each filter must be a dictionary with 'column', 'operator', and 'value' keys.")
            col = f.get("column")
            op = f.get("operator", "=")
            val = f.get("value")

            if not col or col not in valid_columns:
                raise ValidationError(f"Unknown or missing filter column '{col}' for table '{table}'.")

            op_upper = str(op).upper().strip()
            if op_upper not in ALLOWED_OPERATORS:
                raise ValidationError(f"Unsupported filter operator '{op}'. Allowed operators: {sorted(ALLOWED_OPERATORS)}")

            if op_upper in {"IN", "NOT IN"}:
                if not isinstance(val, (list, tuple)) or not val:
                    raise ValidationError(f"Operator '{op}' requires a non-empty list or tuple of values.")
                placeholders = ", ".join(["?"] * len(val))
                clauses.append(f"{col} {op_upper} ({placeholders})")
                params.extend(val)
            else:
                clauses.append(f"{col} {op_upper} ?")
                params.append(val)

        return " WHERE " + " AND ".join(clauses), params

    def list_tables(self) -> list[str]:
        with self.connect() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            rows = cursor.fetchall()
            return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        valid_tables = self.list_tables()
        self._validate_table(table, valid_tables)

        with self.connect() as conn:
            cursor = conn.execute(f"PRAGMA table_info({table});")
            columns = []
            for row in cursor.fetchall():
                columns.append({
                    "cid": row["cid"],
                    "name": row["name"],
                    "type": row["type"],
                    "notnull": bool(row["notnull"]),
                    "default_value": row["dflt_value"],
                    "primary_key": bool(row["pk"]),
                })

            fk_cursor = conn.execute(f"PRAGMA foreign_key_list({table});")
            foreign_keys = []
            for row in fk_cursor.fetchall():
                foreign_keys.append({
                    "table": row["table"],
                    "from": row["from"],
                    "to": row["to"],
                    "on_delete": row["on_delete"],
                })

        return {
            "table": table,
            "columns": columns,
            "foreign_keys": foreign_keys,
        }

    def get_full_schema(self) -> dict[str, Any]:
        tables = self.list_tables()
        schema_map = {}
        for table in tables:
            schema_map[table] = self.get_table_schema(table)
        return {"database": str(self.db_path.name), "tables": schema_map}

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        valid_tables = self.list_tables()
        self._validate_table(table, valid_tables)

        valid_columns = self._get_columns_for_table(table)

        if columns is not None:
            if not isinstance(columns, list):
                raise ValidationError("Columns parameter must be a list of column strings.")
            if not columns:
                raise ValidationError("If columns list is provided, it cannot be empty.")
            self._validate_columns(table, columns, valid_columns)
            select_cols = ", ".join(columns)
        else:
            select_cols = "*"

        try:
            limit_val = int(limit)
            offset_val = int(offset)
        except (ValueError, TypeError):
            raise ValidationError("Limit and offset must be integers.")

        if limit_val < 1:
            raise ValidationError("Limit must be at least 1.")
        if limit_val > MAX_LIMIT:
            limit_val = MAX_LIMIT
        if offset_val < 0:
            raise ValidationError("Offset cannot be negative.")

        where_clause, params = self._build_where_clause(table, filters, valid_columns)

        order_clause = ""
        if order_by:
            if order_by not in valid_columns:
                raise ValidationError(f"Unknown order_by column '{order_by}' in table '{table}'.")
            direction = "DESC" if descending else "ASC"
            order_clause = f" ORDER BY {order_by} {direction}"

        count_sql = f"SELECT COUNT(*) as count FROM {table}{where_clause}"
        query_sql = f"SELECT {select_cols} FROM {table}{where_clause}{order_clause} LIMIT ? OFFSET ?"
        query_params = list(params) + [limit_val, offset_val]

        with self.connect() as conn:
            total_count = conn.execute(count_sql, params).fetchone()["count"]
            cursor = conn.execute(query_sql, query_params)
            rows = [dict(row) for row in cursor.fetchall()]

        has_more = (offset_val + len(rows)) < total_count
        next_offset = (offset_val + len(rows)) if has_more else None

        return {
            "table": table,
            "rows": rows,
            "pagination": {
                "limit": limit_val,
                "offset": offset_val,
                "returned_count": len(rows),
                "total_count": total_count,
                "has_more": has_more,
                "next_offset": next_offset,
            },
        }

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        valid_tables = self.list_tables()
        self._validate_table(table, valid_tables)

        if not values or not isinstance(values, dict):
            raise ValidationError("Insert values must be a non-empty dictionary of column: value pairs.")

        valid_columns = self._get_columns_for_table(table)
        self._validate_columns(table, list(values.keys()), valid_columns)

        cols = list(values.keys())
        placeholders = ", ".join(["?"] * len(cols))
        col_string = ", ".join(cols)
        sql = f"INSERT INTO {table} ({col_string}) VALUES ({placeholders})"
        params = [values[c] for c in cols]

        with self.connect() as conn:
            try:
                cursor = conn.execute(sql, params)
                conn.commit()
                last_id = cursor.lastrowid
            except sqlite3.IntegrityError as e:
                raise ValidationError(f"Database integrity error during insert: {e}")

        # Fetch and return the inserted record
        pk_col = "id" if "id" in valid_columns else cols[0]
        with self.connect() as conn:
            if "id" in valid_columns and last_id:
                row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (last_id,)).fetchone()
            else:
                # Fallback matching by inserted values
                where_parts = " AND ".join([f"{c} = ?" for c in cols])
                row = conn.execute(f"SELECT * FROM {table} WHERE {where_parts}", params).fetchone()

        result_payload = dict(row) if row else {"inserted_id": last_id, **values}
        return {
            "status": "success",
            "table": table,
            "inserted_record": result_payload,
        }

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict[str, Any]] | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        valid_tables = self.list_tables()
        self._validate_table(table, valid_tables)

        if not metric or not isinstance(metric, str):
            raise ValidationError("Metric must be a string.")

        metric_lower = metric.lower().strip()
        if metric_lower not in ALLOWED_METRICS:
            raise ValidationError(f"Unsupported aggregate metric '{metric}'. Allowed metrics: {sorted(ALLOWED_METRICS)}")

        valid_columns = self._get_columns_for_table(table)

        if metric_lower != "count" and not column:
            raise ValidationError(f"Metric '{metric}' requires a valid target column.")

        if column:
            if column not in valid_columns:
                raise ValidationError(f"Unknown column '{column}' in table '{table}'.")
            target_expr = f"{metric_upper_expr(metric_lower)}({column})"
        else:
            target_expr = "COUNT(*)"

        where_clause, params = self._build_where_clause(table, filters, valid_columns)

        group_clause = ""
        select_clause = f"{target_expr} AS value"
        if group_by:
            if group_by not in valid_columns:
                raise ValidationError(f"Unknown group_by column '{group_by}' in table '{table}'.")
            group_clause = f" GROUP BY {group_by}"
            select_clause = f"{group_by}, {select_clause}"

        sql = f"SELECT {select_clause} FROM {table}{where_clause}{group_clause}"

        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            rows = [dict(row) for row in cursor.fetchall()]

        return {
            "table": table,
            "metric": metric_lower,
            "target_column": column or "*",
            "group_by": group_by,
            "results": rows,
        }


def metric_upper_expr(metric: str) -> str:
        return metric.upper()


class PostgreSQLAdapter(DatabaseAdapter):
    """
    PostgreSQL adapter structure demonstrating multi-database support behind a shared interface.
    Can be activated via DATABASE_URL when psycopg/psycopg2 is installed.
    """

    def __init__(self, db_url: str):
        self.db_url = db_url

    def connect(self) -> Any:
        try:
            import psycopg
            return psycopg.connect(self.db_url)
        except ImportError:
            try:
                import psycopg2
                return psycopg2.connect(self.db_url)
            except ImportError:
                raise NotImplementedError(
                    "PostgreSQL drivers (psycopg or psycopg2) are not installed. "
                    "Install with `pip install psycopg` to enable PostgreSQL support."
                )

    def list_tables(self) -> list[str]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")

    def get_table_schema(self, table: str) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")

    def get_full_schema(self) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")

    def search(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")

    def insert(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")

    def aggregate(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise NotImplementedError("PostgreSQL adapter requires active Postgres server connection.")


def get_adapter(db_url_or_path: str | Path | None = None) -> DatabaseAdapter:
    """
    Factory function to return the appropriate DatabaseAdapter based on connection string or environment.
    """
    import os
    target = str(db_url_or_path or os.getenv("DATABASE_URL") or "").strip()
    if target.startswith("postgres://") or target.startswith("postgresql://"):
        return PostgreSQLAdapter(target)
    return SQLiteAdapter(db_url_or_path)
