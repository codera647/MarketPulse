-- API-created Neon roles inherit neon_superuser. Use SQL-created app roles.
-- Passwords/login are provisioned privately after verifying these privileges.
-- This initial migration is for a new dedicated project; it intentionally
-- rejects existing role names instead of silently modifying unrelated roles.
CREATE ROLE marketpulse_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS;
CREATE ROLE marketpulse_worker NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
  NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE marketpulse TO marketpulse_reader, marketpulse_worker;
ALTER ROLE marketpulse_reader SET statement_timeout = '10s';
ALTER ROLE marketpulse_reader SET default_transaction_read_only = on;
ALTER ROLE marketpulse_worker SET statement_timeout = '30s';
ALTER ROLE marketpulse_worker SET idle_in_transaction_session_timeout = '30s';
