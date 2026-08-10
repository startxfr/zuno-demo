# Sales Data Model

The authoritative source reference is the supplied legacy SXA schema. The PostgreSQL target preserves the business flow `affaire -> devis -> commande -> facture` and corresponding line-item tables, on the same HA PostgreSQL cluster described in `docs/architecture/data-architecture.md`. See `MEMORY.md` for source-derived schema details.
