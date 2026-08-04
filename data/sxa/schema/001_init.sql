-- Zuno Demo — SXA sales-operations schema (PostgreSQL-native target)
--
-- This is a from-scratch PostgreSQL schema for the "sales operations" domain
-- described in MEMORY.md section 10 ("SXA commercial database — source-derived
-- schema memory"). It is informed by the legacy MySQL 5.0.95 phpMyAdmin schema
-- prose (table/column names such as `affaire`, `devis`, `commande`, `facture`)
-- but is NOT a literal migration of a real dump — no such dump exists in this
-- repository (ADR-0016, ADR-0025). See data/sxa/migrations/README.md for the
-- full rationale and the legacy-name-to-native-name mapping table.
--
-- MySQL -> PostgreSQL modernizations applied throughout this file (per the
-- "PostgreSQL migration requirements" called out in MEMORY.md section 10):
--   * AUTO_INCREMENT                 -> GENERATED ALWAYS AS IDENTITY
--   * enum('0','1')                  -> native boolean
--   * legacy integer display widths  -> dropped (native integer/bigint/numeric)
--   * tinyint semantics               -> boolean or a checked lookup table
--   * MySQL zero dates (0000-00-00)  -> nullable timestamptz/date, no sentinel
--   * legacy TIMESTAMP default weirdness -> timestamptz DEFAULT now()
--   * implicit (indexed-only) relationships -> explicit FOREIGN KEY constraints
--
-- Domain flow (MEMORY.md section 10): customer -> opportunity -> quote ->
-- order -> invoice, i.e. legacy `entreprise -> affaire -> devis -> commande
-- -> facture`.
--
-- All identifiers use plain, descriptive English names rather than the
-- legacy French/abbreviated column suffixes (e.g. `commercial_aff` becomes
-- `owner_username`) since this is a native target schema, not a literal
-- column-for-column port.

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- users — legacy `user` table (keyed by `login`)
-- ---------------------------------------------------------------------------
-- The legacy password column is intentionally NOT carried forward. Per
-- MEMORY.md: "the PostgreSQL demo model should map authenticated Keycloak
-- subject/email to the legacy sales owner identity rather than trust the
-- legacy password column." `username` is the stable natural key referenced
-- by `owner_username` columns throughout this schema; `keycloak_subject` is
-- the join point to the identity provider (ADR-0012, ADR-0013) once wired.
CREATE TABLE IF NOT EXISTS users (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username            text        NOT NULL UNIQUE,
    email               text        NOT NULL UNIQUE,
    display_name        text        NOT NULL,
    keycloak_subject     text        UNIQUE,
    is_sales_admin      boolean     NOT NULL DEFAULT false,
    is_active           boolean     NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE users IS 'Legacy SXA `user` table, migrated: identity now maps to Keycloak rather than a local password.';

-- ---------------------------------------------------------------------------
-- customers — legacy `entreprise`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS customers (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            text        NOT NULL,
    legal_name      text,
    industry        text,
    address_line1   text,
    address_line2   text,
    postal_code     text,
    city            text,
    country         text,
    website         text,
    phone           text,
    notes           text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE customers IS 'Legacy SXA `entreprise` — company/customer identity and address/business metadata.';

-- ---------------------------------------------------------------------------
-- contacts — legacy `contact`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS contacts (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id     bigint      NOT NULL REFERENCES customers (id) ON DELETE CASCADE,
    first_name      text        NOT NULL,
    last_name       text        NOT NULL,
    email           text,
    phone           text,
    title           text,
    is_primary      boolean     NOT NULL DEFAULT false,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_contacts_customer_id ON contacts (customer_id);

COMMENT ON TABLE contacts IS 'Legacy SXA `contact` — contacts linked to companies.';

-- ---------------------------------------------------------------------------
-- Status lookup tables — legacy `ref_statusaffaire`, `ref_statusdevis`,
-- `ref_statuscommande`, `ref_statusfacture`
-- ---------------------------------------------------------------------------
-- `is_closed`/`is_billable` flags give the access-policy layer (MEMORY.md
-- section 11: Comage/Advantage/Finage visibility rules) a stable, queryable
-- signal instead of string-matching status codes.

CREATE TABLE IF NOT EXISTS opportunity_statuses (
    id          smallint    PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    label       text        NOT NULL,
    is_closed   boolean     NOT NULL DEFAULT false,
    sort_order  smallint    NOT NULL
);

INSERT INTO opportunity_statuses (id, code, label, is_closed, sort_order) VALUES
    (1, 'prospecting',  'Prospecting',  false, 10),
    (2, 'qualification', 'Qualification', false, 20),
    (3, 'proposal',      'Proposal sent', false, 30),
    (4, 'negotiation',   'Negotiation',   false, 40),
    (5, 'won',           'Won',           true,  50),
    (6, 'lost',          'Lost',          true,  60)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS quote_statuses (
    id          smallint    PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    label       text        NOT NULL,
    is_closed   boolean     NOT NULL DEFAULT false,
    sort_order  smallint    NOT NULL
);

INSERT INTO quote_statuses (id, code, label, is_closed, sort_order) VALUES
    (1, 'draft',    'Draft',           false, 10),
    (2, 'sent',     'Sent to client',  false, 20),
    (3, 'accepted', 'Accepted',        true,  30),
    (4, 'rejected', 'Rejected',        true,  40),
    (5, 'expired',  'Expired',         true,  50)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS order_statuses (
    id              smallint    PRIMARY KEY,
    code            text        NOT NULL UNIQUE,
    label           text        NOT NULL,
    -- "Advantage sees business at client-PO-received / administration states
    -- and later" (MEMORY.md section 11).
    is_administration_visible boolean NOT NULL DEFAULT false,
    is_closed       boolean     NOT NULL DEFAULT false,
    sort_order      smallint    NOT NULL
);

INSERT INTO order_statuses (id, code, label, is_administration_visible, is_closed, sort_order) VALUES
    (1, 'draft',                'Draft',                 false, false, 10),
    (2, 'client_po_received',   'Client PO received',    true,  false, 20),
    (3, 'in_administration',    'In administration',     true,  false, 30),
    (4, 'in_production',        'In production',         true,  false, 40),
    (5, 'delivered',            'Delivered',             true,  true,  50),
    (6, 'cancelled',            'Cancelled',              true,  true,  60)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS invoice_statuses (
    id          smallint    PRIMARY KEY,
    code        text        NOT NULL UNIQUE,
    label       text        NOT NULL,
    -- "Finage sees billable (`A facturer`) and invoiced states" (MEMORY.md
    -- section 11). `to_invoice` is the PostgreSQL-native name for the legacy
    -- `A facturer` state.
    is_billable_visible boolean NOT NULL DEFAULT false,
    is_closed   boolean     NOT NULL DEFAULT false,
    sort_order  smallint    NOT NULL
);

INSERT INTO invoice_statuses (id, code, label, is_billable_visible, is_closed, sort_order) VALUES
    (1, 'draft',        'Draft',              false, false, 10),
    (2, 'to_invoice',   'To invoice (A facturer)', true, false, 20),
    (3, 'sent',         'Sent',               true,  false, 30),
    (4, 'paid',         'Paid',               true,  true,  40),
    (5, 'overdue',      'Overdue',            true,  false, 50),
    (6, 'cancelled',    'Cancelled',          true,  true,  60)
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- products — legacy `produit`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku                 text        NOT NULL UNIQUE,
    name                text        NOT NULL,
    family              text,
    -- Red Hat-oriented product classification metadata (MEMORY.md section
    -- 10, `produit`). Kept as free-form jsonb since the legacy classification
    -- taxonomy was not fully enumerated in the source description; values in
    -- fixtures are illustrative/synthetic, not a real product catalog.
    classification      jsonb       NOT NULL DEFAULT '{}'::jsonb,
    list_unit_price     numeric(12,2) NOT NULL DEFAULT 0,
    is_active           boolean     NOT NULL DEFAULT true,
    created_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE products IS 'Legacy SXA `produit` — product catalog, family, price and classification metadata.';

-- ---------------------------------------------------------------------------
-- product_supplier_prices — legacy `produit_fournisseur`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS product_supplier_prices (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id              bigint      NOT NULL REFERENCES products (id) ON DELETE CASCADE,
    supplier_name           text        NOT NULL,
    supplier_unit_price     numeric(12,2) NOT NULL,
    supplier_discount_pct   numeric(5,2)  NOT NULL DEFAULT 0,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_product_supplier_prices_product_id ON product_supplier_prices (product_id);

COMMENT ON TABLE product_supplier_prices IS 'Legacy SXA `produit_fournisseur` — supplier-specific product price and rebate.';

-- ---------------------------------------------------------------------------
-- opportunities — legacy `affaire`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS opportunities (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference               text        NOT NULL UNIQUE,
    customer_id             bigint      NOT NULL REFERENCES customers (id),
    primary_contact_id      bigint      REFERENCES contacts (id),
    name                    text        NOT NULL,
    status_id               smallint    NOT NULL REFERENCES opportunity_statuses (id),
    -- legacy `commercial_aff` / `technique_aff`
    owner_username          text        NOT NULL REFERENCES users (username),
    technical_owner_username text       REFERENCES users (username),
    detected_on             date,
    due_on                  date,
    budget_amount           numeric(12,2),
    drive_url               text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_opportunities_customer_id ON opportunities (customer_id);
CREATE INDEX IF NOT EXISTS ix_opportunities_owner_username ON opportunities (owner_username);
CREATE INDEX IF NOT EXISTS ix_opportunities_status_id ON opportunities (status_id);

COMMENT ON TABLE opportunities IS 'Legacy SXA `affaire` — opportunity/business case, owner, status, budget, deadlines and Drive reference.';

-- ---------------------------------------------------------------------------
-- quotes — legacy `devis`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quotes (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference           text        NOT NULL UNIQUE,
    opportunity_id      bigint      NOT NULL REFERENCES opportunities (id),
    customer_id         bigint      NOT NULL REFERENCES customers (id),
    contact_id          bigint      REFERENCES contacts (id),
    status_id           smallint    NOT NULL REFERENCES quote_statuses (id),
    owner_username      text        NOT NULL REFERENCES users (username),
    total_amount        numeric(12,2) NOT NULL DEFAULT 0,
    client_po_reference text,
    drive_url           text,
    issued_at           timestamptz,
    modified_at         timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_quotes_opportunity_id ON quotes (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_quotes_owner_username ON quotes (owner_username);
CREATE INDEX IF NOT EXISTS ix_quotes_status_id ON quotes (status_id);

COMMENT ON TABLE quotes IS 'Legacy SXA `devis` — quote, opportunity link, status, commercial owner, total, client PO and Drive reference.';

-- ---------------------------------------------------------------------------
-- quote_lines — legacy `devis_produit`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quote_lines (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quote_id        bigint      NOT NULL REFERENCES quotes (id) ON DELETE CASCADE,
    product_id      bigint      NOT NULL REFERENCES products (id),
    sort_order      smallint    NOT NULL DEFAULT 0,
    quantity        numeric(10,2) NOT NULL DEFAULT 1,
    unit_price      numeric(12,2) NOT NULL,
    discount_pct    numeric(5,2)  NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_quote_lines_quote_id ON quote_lines (quote_id);

COMMENT ON TABLE quote_lines IS 'Legacy SXA `devis_produit` — quote line items, quantity, rebate and sales price.';

-- ---------------------------------------------------------------------------
-- orders — legacy `commande`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS orders (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference               text        NOT NULL UNIQUE,
    quote_id                bigint      NOT NULL REFERENCES quotes (id),
    customer_id             bigint      NOT NULL REFERENCES customers (id),
    contact_id              bigint      REFERENCES contacts (id),
    status_id               smallint    NOT NULL REFERENCES order_statuses (id),
    owner_username          text        NOT NULL REFERENCES users (username),
    sales_total_amount      numeric(12,2) NOT NULL DEFAULT 0,
    supplier_total_amount   numeric(12,2) NOT NULL DEFAULT 0,
    client_po_reference     text,
    drive_url               text,
    recorded_at             timestamptz,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_orders_quote_id ON orders (quote_id);
CREATE INDEX IF NOT EXISTS ix_orders_owner_username ON orders (owner_username);
CREATE INDEX IF NOT EXISTS ix_orders_status_id ON orders (status_id);

COMMENT ON TABLE orders IS 'Legacy SXA `commande` — order, originating quote, status, commercial owner, sales/supplier totals, client PO and Drive reference.';

-- ---------------------------------------------------------------------------
-- order_lines — legacy `commande_produit`
-- ---------------------------------------------------------------------------
-- Carries both customer pricing (unit_price/discount_pct) and supplier
-- pricing (supplier_unit_price/supplier_discount_pct) so margin can be
-- derived from real order economics, per MEMORY.md section 10's explicit
-- note not to invent an artificial product cost_price.
CREATE TABLE IF NOT EXISTS order_lines (
    id                      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id                bigint      NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    product_id              bigint      NOT NULL REFERENCES products (id),
    sort_order               smallint   NOT NULL DEFAULT 0,
    quantity                numeric(10,2) NOT NULL DEFAULT 1,
    unit_price               numeric(12,2) NOT NULL,
    discount_pct             numeric(5,2)  NOT NULL DEFAULT 0,
    supplier_unit_price      numeric(12,2),
    supplier_discount_pct    numeric(5,2)  NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_order_lines_order_id ON order_lines (order_id);

COMMENT ON TABLE order_lines IS 'Legacy SXA `commande_produit` — order line items incl. supplier pricing for margin calculation.';

-- ---------------------------------------------------------------------------
-- invoices — legacy `facture`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoices (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference           text        NOT NULL UNIQUE,
    order_id            bigint      NOT NULL REFERENCES orders (id),
    customer_id         bigint      NOT NULL REFERENCES customers (id),
    contact_id          bigint      REFERENCES contacts (id),
    status_id           smallint    NOT NULL REFERENCES invoice_statuses (id),
    owner_username      text        NOT NULL REFERENCES users (username),
    total_amount        numeric(12,2) NOT NULL DEFAULT 0,
    invoice_type        text        NOT NULL DEFAULT 'standard'
                            CHECK (invoice_type IN ('standard', 'credit_note', 'deposit')),
    sent_on              date,
    payment_due_on        date,
    paid_on              date,
    drive_url            text,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_invoices_order_id ON invoices (order_id);
CREATE INDEX IF NOT EXISTS ix_invoices_owner_username ON invoices (owner_username);
CREATE INDEX IF NOT EXISTS ix_invoices_status_id ON invoices (status_id);

COMMENT ON TABLE invoices IS 'Legacy SXA `facture` — invoice, originating order, status, sales owner, amount, payment conditions, dates, type and Drive reference.';

-- ---------------------------------------------------------------------------
-- invoice_lines — legacy `facture_produit`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS invoice_lines (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_id      bigint      NOT NULL REFERENCES invoices (id) ON DELETE CASCADE,
    product_id      bigint      NOT NULL REFERENCES products (id),
    sort_order      smallint    NOT NULL DEFAULT 0,
    quantity        numeric(10,2) NOT NULL DEFAULT 1,
    unit_price      numeric(12,2) NOT NULL,
    discount_pct    numeric(5,2)  NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_invoice_lines_invoice_id ON invoice_lines (invoice_id);

COMMENT ON TABLE invoice_lines IS 'Legacy SXA `facture_produit` — invoice line items.';

-- ---------------------------------------------------------------------------
-- activities — legacy `actualite`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activities (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at     timestamptz NOT NULL DEFAULT now(),
    activity_type   text        NOT NULL,
    customer_id     bigint      REFERENCES customers (id),
    contact_id      bigint      REFERENCES contacts (id),
    opportunity_id  bigint      REFERENCES opportunities (id),
    quote_id        bigint      REFERENCES quotes (id),
    order_id        bigint      REFERENCES orders (id),
    invoice_id      bigint      REFERENCES invoices (id),
    actor_username  text        REFERENCES users (username),
    summary         text        NOT NULL,
    related_status  text
);

CREATE INDEX IF NOT EXISTS ix_activities_opportunity_id ON activities (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_activities_customer_id ON activities (customer_id);
CREATE INDEX IF NOT EXISTS ix_activities_occurred_at ON activities (occurred_at);

COMMENT ON TABLE activities IS 'Legacy SXA `actualite` — activity/event journal referencing companies, contacts, opportunities, quotes, orders and invoices.';

-- ---------------------------------------------------------------------------
-- calls — legacy `appel`
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calls (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scheduled_at    timestamptz NOT NULL,
    actor_username  text        NOT NULL REFERENCES users (username),
    opportunity_id  bigint      REFERENCES opportunities (id),
    subject         text        NOT NULL,
    notes           text,
    is_reminder     boolean     NOT NULL DEFAULT false,
    completed_at    timestamptz
);

CREATE INDEX IF NOT EXISTS ix_calls_opportunity_id ON calls (opportunity_id);
CREATE INDEX IF NOT EXISTS ix_calls_actor_username ON calls (actor_username);

COMMENT ON TABLE calls IS 'Legacy SXA `appel` — calls and reminders, including user and opportunity references.';

-- Note: the legacy `projet` table ("legacy project/context object") is
-- deliberately NOT migrated. MEMORY.md describes it only in passing with no
-- columns, and nothing in the v0 scope (MCP tools, agents) references it —
-- see data/sxa/migrations/README.md for this decision.
