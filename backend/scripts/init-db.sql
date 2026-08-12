-- Provisioning of the application role.
--
-- Roles are cluster-level objects, so they are created here rather than in a
-- migration: a migration describes one database, and reverting it must not remove a
-- role another database may be using.
--
-- What matters is the split. Migrations connect as the owner (the superuser below);
-- the application connects as `cheatsheet_app`, which owns nothing. PostgreSQL
-- exempts a table's owner from that table's Row-Level Security policies, so without
-- two roles every isolation policy in the system would be decorative — and every
-- test that "proves" tenants are separated would prove nothing at all.
--
-- This file is for LOCAL DEVELOPMENT and CI. The password below is a placeholder for
-- a throwaway container that listens on localhost; staging and production provision
-- the role with a real credential distributed over a private channel
-- (docs/configuration-management.md §4.3).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'cheatsheet_app') THEN
        CREATE ROLE cheatsheet_app LOGIN PASSWORD 'test-only-local-container';
    ELSE
        ALTER ROLE cheatsheet_app LOGIN PASSWORD 'test-only-local-container';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE cheatsheet TO cheatsheet_app;
