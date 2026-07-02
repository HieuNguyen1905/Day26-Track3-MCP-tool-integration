"""
Verification Script for SQLite Lab FastMCP Server.
Automates end-to-end testing of tools, resources, valid executions, and error handling.
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure the package is importable from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from implementation.init_db import create_database
from implementation.mcp_server import aggregate, database_schema, get_db_adapter, insert, mcp, search, table_schema


def print_header(title: str) -> None:
    print("\n" + "=" * 70)
    print(f" [VERIFICATION] {title}")
    print("=" * 70)


def print_step(step_name: str) -> None:
    print(f"\n--- {step_name} ---")


def run_verification() -> bool:
    all_passed = True

    print_header("1. Database Initialization & Adapter Verification")
    try:
        db_path = create_database(force_recreate=True)
        print(f"PASS: Re-initialized test database at: {db_path}")
        adapter = get_db_adapter(db_path)
        tables = adapter.list_tables()
        print(f"PASS: Adapter connected. Discovered tables: {tables}")
        assert set(tables) == {"students", "courses", "enrollments"}, f"Unexpected tables: {tables}"
    except Exception as e:
        print(f"FAIL: Database init error: {e}")
        return False

    print_header("2. Tool & Resource Discovery via FastMCP")
    try:
        tools = asyncio.run(mcp.list_tools())
        tool_names = [t.name for t in tools]
        print(f"PASS: Discovered tools: {tool_names}")
        assert set(tool_names) == {"search", "insert", "aggregate"}, f"Missing required tools: {tool_names}"

        resources = asyncio.run(mcp.list_resources())
        resource_names = [r.uri for r in resources]
        templates = asyncio.run(mcp.list_resource_templates())
        template_names = [t.uri_template for t in templates]
        print(f"PASS: Discovered resources: {resource_names} and templates: {template_names}")
    except Exception as e:
        print(f"FAIL: Tool discovery error: {e}")
        return False

    print_header("3. Valid Tool Execution Demos")
    
    # 3a. Search students in cohort A1
    print_step("3a. Search: All students in cohort 'A1'")
    try:
        res = search(table="students", filters=[{"column": "cohort", "operator": "=", "value": "A1"}], order_by="name")
        print(f"Returned {res['pagination']['returned_count']} rows out of {res['pagination']['total_count']} total.")
        for r in res["rows"]:
            print(f"  - {r['student_id']}: {r['name']} ({r['email']})")
        assert res["pagination"]["returned_count"] == 3
        print("PASS: Search filter and pagination verified.")
    except Exception as e:
        print(f"FAIL: Search execution error: {e}")
        all_passed = False

    # 3b. Insert a new student
    print_step("3b. Insert: Add a new student record")
    try:
        new_student = {
            "student_id": "S9999",
            "name": "Zack Verification",
            "email": "zack.v@example.edu",
            "cohort": "C1",
            "enrollment_year": 2025,
        }
        res = insert(table="students", values=new_student)
        print(f"Insert Status: {res['status']}")
        print(f"Inserted Record: {res['inserted_record']}")
        assert res["inserted_record"]["student_id"] == "S9999"
        print("PASS: Insert verified.")
    except Exception as e:
        print(f"FAIL: Insert execution error: {e}")
        all_passed = False

    # 3c. Count rows in a table
    print_step("3c. Aggregate: Count rows in 'students' table")
    try:
        res = aggregate(table="students", metric="count")
        count_val = res["results"][0]["value"]
        print(f"Student Count: {count_val}")
        assert count_val == 9  # 8 seed + 1 inserted
        print("PASS: Aggregate COUNT verified.")
    except Exception as e:
        print(f"FAIL: Aggregate COUNT error: {e}")
        all_passed = False

    # 3d. Compute average score by course
    print_step("3d. Aggregate: Compute average score by course_code")
    try:
        res = aggregate(table="enrollments", metric="avg", column="score", group_by="course_code")
        print("Average scores per course:")
        for r in res["results"]:
            print(f"  - Course {r['course_code']}: Avg Score = {r['value']:.2f}")
        print("PASS: Aggregate AVG with GROUP BY verified.")
    except Exception as e:
        print(f"FAIL: Aggregate AVG error: {e}")
        all_passed = False

    print_header("4. Resource Reading Demos")
    
    # 4a. Full Database Schema
    print_step("4a. Resource: schema://database")
    try:
        schema_json = database_schema()
        schema_data = json.loads(schema_json)
        print(f"Database name: {schema_data.get('database')}")
        print(f"Tables documented: {list(schema_data.get('tables', {}).keys())}")
        assert "students" in schema_data["tables"]
        print("PASS: Full database schema resource verified.")
    except Exception as e:
        print(f"FAIL: Full schema resource error: {e}")
        all_passed = False

    # 4b. Table Schema
    print_step("4b. Resource: schema://table/students")
    try:
        tbl_json = table_schema(table_name="students")
        tbl_data = json.loads(tbl_json)
        cols = [c["name"] for c in tbl_data.get("columns", [])]
        print(f"Table 'students' columns: {cols}")
        assert "student_id" in cols and "email" in cols
        print("PASS: Table schema resource verified.")
    except Exception as e:
        print(f"FAIL: Table schema resource error: {e}")
        all_passed = False

    print_header("5. Safety & Error Handling Verification")

    # 5a. Unknown Table
    print_step("5a. Reject Unknown Table")
    try:
        search(table="fake_table_123")
        print("FAIL: Expected error for unknown table, but query succeeded.")
        all_passed = False
    except ValueError as e:
        print(f"PASS: Safely rejected unknown table with error: '{e}'")

    # 5b. Unknown Column
    print_step("5b. Reject Unknown Column")
    try:
        search(table="students", columns=["student_id", "secret_social_security_number"])
        print("FAIL: Expected error for unknown column, but query succeeded.")
        all_passed = False
    except ValueError as e:
        print(f"PASS: Safely rejected unknown column with error: '{e}'")

    # 5c. Unsupported Filter Operator
    print_step("5c. Reject Unsupported Filter Operator (SQL Injection Prevention)")
    try:
        search(table="students", filters=[{"column": "name", "operator": "OR 1=1; DROP TABLE students; --", "value": "test"}])
        print("FAIL: Expected error for malicious SQL operator, but query succeeded.")
        all_passed = False
    except ValueError as e:
        print(f"PASS: Safely rejected unsupported operator with error: '{e}'")

    # 5d. Empty Insert
    print_step("5d. Reject Empty Insert Payload")
    try:
        insert(table="students", values={})
        print("FAIL: Expected error for empty insert values, but succeeded.")
        all_passed = False
    except ValueError as e:
        print(f"PASS: Safely rejected empty insert payload with error: '{e}'")

    # 5e. Invalid Aggregate Metric
    print_step("5e. Reject Invalid Aggregate Metric")
    try:
        aggregate(table="students", metric="DELETE_EVERYTHING")
        print("FAIL: Expected error for invalid metric, but succeeded.")
        all_passed = False
    except ValueError as e:
        print(f"PASS: Safely rejected invalid aggregate metric with error: '{e}'")

    print_header("Verification Summary")
    if all_passed:
        print("\n [SUCCESS] ALL 5 VERIFICATION STAGES & ERROR CHECKS PASSED 100%! \n")
        return True
    else:
        print("\n [FAILURE] Some verification checks failed. See output above. \n")
        return False


if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
