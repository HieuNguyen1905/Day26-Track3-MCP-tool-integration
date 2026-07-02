"""
Automated Pytest Test Suite for SQLite Lab FastMCP Server.
Covers all base requirements and bonus features (Postgres stub, validation error wrapping, pagination metadata).
"""

import json
import pytest
from pathlib import Path

from implementation.init_db import create_database
from implementation.db import SQLiteAdapter, PostgreSQLAdapter, ValidationError, get_adapter
from implementation.mcp_server import mcp, search, insert, aggregate, database_schema, table_schema, get_db_adapter


@pytest.fixture(scope="module")
def setup_test_db(tmp_path_factory):
    """Create a temporary SQLite database for clean testing."""
    tmp_dir = tmp_path_factory.mktemp("db")
    db_path = tmp_dir / "test_school.db"
    create_database(db_path=db_path, force_recreate=True)
    get_db_adapter(db_path)
    return db_path


def test_server_foundation(setup_test_db):
    """Test Server Foundation: SQLite adapter initialization and table discovery."""
    adapter = get_db_adapter()
    tables = adapter.list_tables()
    assert set(tables) == {"students", "courses", "enrollments"}
    assert adapter.db_path.exists()


def test_tool_search_and_pagination(setup_test_db):
    """Test required tool: search with filters, sorting, and pagination metadata."""
    res = search(table="students", filters=[{"column": "cohort", "operator": "=", "value": "A1"}], limit=2, order_by="name")
    assert res["table"] == "students"
    assert len(res["rows"]) == 2
    assert res["pagination"]["returned_count"] == 2
    assert res["pagination"]["total_count"] == 3
    assert res["pagination"]["has_more"] is True
    assert res["pagination"]["next_offset"] == 2


def test_tool_insert(setup_test_db):
    """Test required tool: insert valid record and verify auto-generated ID and payload."""
    new_course = {
        "course_code": "SEC401",
        "title": "Cybersecurity Fundamentals",
        "department": "Computer Science",
        "credits": 3
    }
    res = insert(table="courses", values=new_course)
    assert res["status"] == "success"
    assert res["inserted_record"]["course_code"] == "SEC401"
    assert "id" in res["inserted_record"]

    # Verify insertion via search
    search_res = search(table="courses", filters=[{"column": "course_code", "operator": "=", "value": "SEC401"}])
    assert len(search_res["rows"]) == 1


def test_tool_aggregate(setup_test_db):
    """Test required tool: aggregate supporting count, avg, sum, min, max and group_by."""
    count_res = aggregate(table="courses", metric="count")
    assert count_res["results"][0]["value"] == 6  # 5 seed + 1 inserted above

    avg_res = aggregate(table="enrollments", metric="avg", column="score", group_by="grade")
    assert len(avg_res["results"]) > 0
    for r in avg_res["results"]:
        assert "grade" in r and "value" in r


def test_resources_schema(setup_test_db):
    """Test required resources: full database schema and dynamic per-table schema template."""
    full_json = database_schema()
    full_data = json.loads(full_json)
    assert "database" in full_data
    assert "students" in full_data["tables"]

    tbl_json = table_schema(table_name="courses")
    tbl_data = json.loads(tbl_json)
    assert tbl_data["table"] == "courses"
    cols = [c["name"] for c in tbl_data["columns"]]
    assert "course_code" in cols and "credits" in cols


def test_safety_and_error_handling(setup_test_db):
    """Test safety: reject invalid table/column names, unsupported operators, empty inserts, and bad metrics."""
    with pytest.raises(ValueError, match="Unknown table"):
        search(table="non_existent_table")

    with pytest.raises(ValueError, match="Unknown column"):
        search(table="students", columns=["student_id", "bad_col"])

    with pytest.raises(ValueError, match="Unsupported filter operator"):
        search(table="students", filters=[{"column": "name", "operator": "INVALID_OP", "value": "test"}])

    with pytest.raises(ValueError, match="Insert values must be a non-empty dictionary"):
        insert(table="students", values={})

    with pytest.raises(ValueError, match="Unsupported aggregate metric"):
        aggregate(table="students", metric="DESTROY")


def test_bonus_shared_interface():
    """Test Bonus: Shared interface supporting SQLite and PostgreSQL backend switching."""
    sqlite_adapter = get_adapter("test_dummy.db")
    assert isinstance(sqlite_adapter, SQLiteAdapter)

    postgres_adapter = get_adapter("postgres://user:pass@localhost:5432/testdb")
    assert isinstance(postgres_adapter, PostgreSQLAdapter)
    
    with pytest.raises(NotImplementedError):
        postgres_adapter.list_tables()
