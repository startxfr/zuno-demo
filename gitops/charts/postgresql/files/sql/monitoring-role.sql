DO $mrole$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ccp_monitoring') THEN
    CREATE ROLE ccp_monitoring LOGIN PASSWORD :'pass';
  ELSE
    ALTER ROLE ccp_monitoring PASSWORD :'pass';
  END IF;
END
$mrole$;
GRANT pg_monitor TO ccp_monitoring;
GRANT CONNECT ON DATABASE postgres TO ccp_monitoring;
