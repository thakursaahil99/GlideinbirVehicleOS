"""
Database-level immutability for audit logs: PostgreSQL rejects any UPDATE or
DELETE on the table, even from raw SQL. (TRUNCATE, used by test teardown and
deliberate maintenance, is not affected.)
"""
from django.db import migrations

CREATE_SQL = """
CREATE OR REPLACE FUNCTION audit_logs_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_logs_auditlog is append-only (% blocked)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS audit_logs_auditlog_immutable ON audit_logs_auditlog;
CREATE TRIGGER audit_logs_auditlog_immutable
    BEFORE UPDATE OR DELETE ON audit_logs_auditlog
    FOR EACH ROW EXECUTE FUNCTION audit_logs_block_mutation();
"""

DROP_SQL = """
DROP TRIGGER IF EXISTS audit_logs_auditlog_immutable ON audit_logs_auditlog;
DROP FUNCTION IF EXISTS audit_logs_block_mutation();
"""


def _run(sql):
    def apply(apps, schema_editor):
        if schema_editor.connection.vendor == "postgresql":
            schema_editor.execute(sql, params=None)  # no interpolation: the SQL contains a literal %

    return apply


class Migration(migrations.Migration):
    dependencies = [("audit_logs", "0001_initial")]

    operations = [migrations.RunPython(_run(CREATE_SQL), _run(DROP_SQL))]
