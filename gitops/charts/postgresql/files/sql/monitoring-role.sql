SELECT format('CREATE ROLE ccp_monitoring LOGIN PASSWORD %L', :'pass')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ccp_monitoring') \gexec

ALTER ROLE ccp_monitoring PASSWORD :'pass';
GRANT pg_monitor TO ccp_monitoring;
GRANT CONNECT ON DATABASE postgres TO ccp_monitoring;
