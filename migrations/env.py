"""Alembic uses the caller's connection; no credential-bearing ini URL."""
from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Use python -m manage db-upgrade to run migrations")
context.configure(connection=connection)
with context.begin_transaction():
    context.run_migrations()
