SELECT format('CREATE ROLE ccp_monitoring LOGIN PASSWORD %L', :'pass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ccp_monitoring') \gexec

ALTER ROLE ccp_monitoring PASSWORD :'pass';
GRANT pg_monitor TO ccp_monitoring;
GRANT CONNECT ON DATABASE postgres TO ccp_monitoring;

-- The "monitor" schema PGO 5.8.8's pgMonitor step blindly targets even on
-- pg18. Its absence is not cosmetic: that psql error aborts the whole PGO
-- reconcile (exit code 3) before the databaseInitSQL step, so
-- spec.databaseInitSQL (all the CREATE EXTENSION vector statements) never
-- runs on a fresh cluster (live-verified 2026-08-25: creating this schema
-- unwedged the reconcile and PGO applied init.sql within seconds).
CREATE SCHEMA IF NOT EXISTS monitor AUTHORIZATION ccp_monitoring;
