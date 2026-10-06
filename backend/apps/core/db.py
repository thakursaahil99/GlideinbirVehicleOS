from django.db import connection
from django.db.models import Q


def json_list_contains(field, value):
    """
    ``field`` (a JSON list) contains ``value``. Uses PostgreSQL's ``@>`` operator;
    falls back to a quoted substring match on SQLite (local experiments only).
    """
    if connection.vendor == "postgresql":
        return Q(**{f"{field}__contains": [value]})
    return Q(**{f"{field}__icontains": f'"{value}"'})
