# Migrations

The schema is managed by Alembic. To create a new migration after changing models:

```bash
alembic revision --autogenerate -m "add fancy new column"
alembic upgrade head
```

CI runs `alembic check` to fail PRs that change models without a matching migration.
