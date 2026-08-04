# SXA migrations

## What this is, and what it is not

This directory (together with `data/sxa/schema/` and `data/sxa/fixtures/`)
implements ADR-0016 ("Migrate the legacy SXA schema to PostgreSQL"). It is a
**from-scratch, PostgreSQL-native schema** for the sales-operations domain
described in `MEMORY.md` section 10 ("SXA commercial database - source-derived
schema memory"), not a literal migration of a real database dump.

There is no legacy MySQL dump in this repository, and there never should be
one (ADR-0025: "keep sensitive and real commercial data outside the public
repository"). The only source material available to this track was a prose
description, in `MEMORY.md`, of a legacy phpMyAdmin schema export for MySQL
5.0.95 - table names, key columns, the commercial state-machine flow, and a
list of known MySQL-specific constructs that needed modernizing. That
description was treated as a **migration source**, per ADR-0016, and used to
design a native target schema; it was not imported, transpiled, or
mechanically converted.

If a real SXA dump is ever made available in a controlled, non-public
location, a proper `pgloader`/ETL-based migration path from that dump to
this schema is future work - out of scope for this v0 demo.

## Where things live

- `data/sxa/schema/001_init.sql` - the sales-operations tables (customers,
  contacts, opportunities, quotes, orders, invoices, products, activities,
  calls) and their status lookup tables.
- `data/sxa/schema/002_pgvector.sql` - the `document_embeddings` table used
  by the RAG service (Track D), unrelated to the SXA domain itself but
  co-located here because it shares the same PostgreSQL instance (ADR-0015).
- `data/sxa/fixtures/seed.sql` - synthetic demo data, safe to commit
  (ADR-0025).

`ansible/roles/sql_schema` applies these files, in order, against the
CloudNativePG-managed cluster provisioned by `ansible/roles/postgresql`.

## Legacy table -> native table mapping

| Legacy (MySQL, from MEMORY.md) | Native PostgreSQL table | Notes |
|---|---|---|
| `entreprise` | `customers` | company/customer identity |
| `contact` | `contacts` | linked to `customers` |
| `affaire` | `opportunities` | `id_aff` -> `id`, `entreprise_aff`/`contact_aff` -> FKs, `commercial_aff`/`technique_aff` -> `owner_username`/`technical_owner_username`, `detect_aff`/`echeance_aff`/`budget_aff` -> `detected_on`/`due_on`/`budget_amount`, `gdrive_aff` -> `drive_url` |
| `devis` | `quotes` | `sommeHT_dev` -> `total_amount`, `BDCclient_dev` -> `client_po_reference`, `daterecord_dev`/`datemodif_dev` -> `issued_at`/`modified_at` |
| `devis_produit` | `quote_lines` | quantity/rebate/sales price line items |
| `commande` | `orders` | `sommeHT_cmd`/`sommeFHT_cmd` -> `sales_total_amount`/`supplier_total_amount` |
| `commande_produit` | `order_lines` | keeps both customer pricing (`prix`/`remise`) and supplier pricing (`prixF`/`remiseF`) per line, so margin is derived from real order economics rather than an invented product cost - MEMORY.md is explicit that this is deliberate |
| `facture` | `invoices` | `sommeHT_fact` -> `total_amount`, `dateenvoi_fact`/`datereglement_fact` -> `sent_on`/`paid_on`, `type_fact` -> `invoice_type` |
| `facture_produit` | `invoice_lines` | |
| `produit` | `products` | `classification` jsonb captures the "Red Hat-oriented product classification metadata" MEMORY.md describes; fixture values are illustrative, not a real catalog |
| `produit_fournisseur` | `product_supplier_prices` | |
| `actualite` | `activities` | polymorphic references to customer/contact/opportunity/quote/order/invoice, kept as nullable FKs rather than a generic `(type, id)` pair, since PostgreSQL can enforce real foreign keys here |
| `appel` | `calls` | |
| `user` | `users` | password column dropped entirely - see below |
| `ref_statusaffaire` | `opportunity_statuses` | adds `is_closed` for policy queries |
| `ref_statusdevis` | `quote_statuses` | adds `is_closed` |
| `ref_statuscommande` | `order_statuses` | adds `is_administration_visible` (Advantage visibility, MEMORY.md section 11) and `is_closed` |
| `ref_statusfacture` | `invoice_statuses` | adds `is_billable_visible` (Finage visibility - the legacy `A facturer` state maps to the `to_invoice` code) and `is_closed` |
| `projet` | *(not migrated)* | MEMORY.md describes this only as a "legacy project/context object" with no columns, and nothing in v0 scope (MCP tools, agents, policies) references it. Deliberately dropped rather than guessed at; revisit if a concrete v1 need appears. |

## Identity mapping

The legacy `user` table's `login`/password model is not carried forward.
`users.username` is the stable natural key every `owner_username` /
`actor_username` column references; `users.keycloak_subject` is the join
point to the identity provider once Keycloak-issued tokens are propagated to
this layer (ADR-0012, ADR-0013). No password hash of any kind exists in this
schema - authentication is Keycloak's job, not this database's.

## MySQL -> PostgreSQL construct changes

Per the "PostgreSQL migration requirements" in `MEMORY.md` section 10, every
occurrence of the following legacy MySQL 5.0-era constructs was replaced:

| Legacy MySQL construct | PostgreSQL replacement |
|---|---|
| `AUTO_INCREMENT` | `GENERATED ALWAYS AS IDENTITY` |
| `enum('0','1')` | native `boolean` |
| legacy integer display widths (e.g. `int(11)`) | plain `integer`/`bigint` (display width is not a PostgreSQL concept) |
| `tinyint` used as a boolean/flag | native `boolean`, or a small `CHECK`-constrained lookup table for multi-valued status columns |
| MySQL zero dates (`0000-00-00`) | nullable `date`/`timestamptz` - "unknown" is represented as `NULL`, never a sentinel date |
| legacy `TIMESTAMP` auto-update defaults | `timestamptz NOT NULL DEFAULT now()`, set explicitly rather than relying on implicit MySQL behavior |
| implicit relationships (indexed but not FK-constrained) | explicit `FOREIGN KEY` constraints with a matching index on every FK column |

## Fixtures

`data/sxa/fixtures/seed.sql` contains ~40 rows of obviously synthetic
business data (5 fictional companies, 5 fictional contacts, a handful of
opportunities/quotes/orders/invoices and their line items) plus reference
data. Every company and person name is invented for this demo; nothing in
this file is derived from, or resembles, a real customer, contact or deal.
See ADR-0025.
