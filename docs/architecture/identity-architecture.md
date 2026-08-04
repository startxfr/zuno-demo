# Identity Architecture

Keycloak is the central identity provider. Google Workspace is federated with Keycloak. Agent access uses groups such as `agent_comage` and `agent_tekos`; privileged sales access uses `sales_admin`.

End-user identity is propagated through BFF and runtime boundaries. Google Workspace tools use delegated OAuth2 user authorization so source ACLs remain effective.
