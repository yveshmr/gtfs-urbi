from typing import Any

APPLICATION_SCHEMAS = frozenset(
    {
        "analytics",
        "audit",
        "core",
        "raw",
        "realtime",
    }
)


def include_application_object(
    name: str | None,
    type_: str,
    parent_names: dict[str, Any],
) -> bool:
    """Limit Alembic reflection to database objects owned by the application."""
    if type_ == "schema":
        return name in APPLICATION_SCHEMAS

    if type_ == "table":
        return parent_names.get("schema_name") in APPLICATION_SCHEMAS

    return True
