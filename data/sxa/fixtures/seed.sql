-- Zuno Demo - SXA sales-operations synthetic fixtures
--
-- Every company, person, deal and amount in this file is fictional and
-- invented for this demo. None of it represents real customers, contacts,
-- deals or commercial terms (ADR-0025). Run after data/sxa/schema/001_init.sql
-- and data/sxa/schema/002_pgvector.sql against an empty database.
--
-- Foreign keys are resolved via natural-key subqueries (reference/SKU/email)
-- rather than hardcoded identity values so this file stays correct
-- regardless of insertion order or IDENTITY sequence state.

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
INSERT INTO users (username, email, display_name, is_sales_admin, is_active) VALUES
    ('a.dubois', 'a.dubois@zuno-demo.example', 'Aline Dubois', false, true),
    ('t.lemoine', 't.lemoine@zuno-demo.example', 'Théo Lemoine', false, true),
    ('l.fontaine', 'l.fontaine@zuno-demo.example', 'Léa Fontaine', true, true),
    ('s.moreau', 's.moreau@zuno-demo.example', 'Sacha Moreau', false, true),
    ('n.bakr', 'n.bakr@zuno-demo.example', 'Nadia Bakr', false, true)
ON CONFLICT (username) DO NOTHING;

-- ---------------------------------------------------------------------------
-- customers
-- ---------------------------------------------------------------------------
INSERT INTO customers (name, legal_name, industry, address_line1, postal_code, city, country, website, phone) VALUES
    ('Nimbus Cloud Works', 'Nimbus Cloud Works SAS', 'Cloud infrastructure', '12 Rue des Nuages', '75012', 'Paris', 'France', 'https://nimbus-cloud.example', '+33 1 00 00 00 01'),
    ('Solstice Robotics', 'Solstice Robotics SARL', 'Industrial automation', '4 Avenue des Automates', '69003', 'Lyon', 'France', 'https://solstice-robotics.example', '+33 4 00 00 00 02'),
    ('Meridian Foodware', 'Meridian Foodware SA', 'Food distribution software', '9 Boulevard Meridien', '31000', 'Toulouse', 'France', 'https://meridian-foodware.example', '+33 5 00 00 00 03'),
    ('Cobalt Analytics', 'Cobalt Analytics SAS', 'Data analytics', '21 Rue Cobalt', '44000', 'Nantes', 'France', 'https://cobalt-analytics.example', '+33 2 00 00 00 04'),
    ('Fictive Aerodynamics', 'Fictive Aerodynamics SA', 'Aerospace engineering', '3 Allee des Turbines', '33700', 'Bordeaux', 'France', 'https://fictive-aero.example', '+33 5 00 00 00 05')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- contacts (one primary contact per customer)
-- ---------------------------------------------------------------------------
INSERT INTO contacts (customer_id, first_name, last_name, email, phone, title, is_primary)
SELECT c.id, v.first_name, v.last_name, v.email, v.phone, v.title, true
FROM (VALUES
    ('Nimbus Cloud Works', 'Alix', 'Rennard', 'alix.rennard@nimbus-cloud.example', '+33 6 00 00 01 01', 'Chief Technology Officer'),
    ('Solstice Robotics', 'Hugo', 'Werner', 'hugo.werner@solstice-robotics.example', '+33 6 00 00 02 01', 'Head of Operations'),
    ('Meridian Foodware', 'Camille', 'Ostrowski', 'camille.ostrowski@meridian-foodware.example', '+33 6 00 00 03 01', 'IT Director'),
    ('Cobalt Analytics', 'Ravi', 'Sundaram', 'ravi.sundaram@cobalt-analytics.example', '+33 6 00 00 04 01', 'VP Engineering'),
    ('Fictive Aerodynamics', 'Ines', 'Castellano', 'ines.castellano@fictive-aero.example', '+33 6 00 00 05 01', 'Chief Financial Officer')
) AS v(customer_name, first_name, last_name, email, phone, title)
JOIN customers c ON c.name = v.customer_name
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- products
-- ---------------------------------------------------------------------------
INSERT INTO products (sku, name, family, classification, list_unit_price) VALUES
    ('OSP-STD', 'OpenShift Platform Support - Standard', 'platform-support', '{"category":"container-platform","tier":"standard"}', 12000.00),
    ('OSP-PREM', 'OpenShift Platform Support - Premium', 'platform-support', '{"category":"container-platform","tier":"premium"}', 24000.00),
    ('AAP-SUB', 'Automation Platform Subscription', 'automation', '{"category":"automation","tier":"standard"}', 8000.00),
    ('AI-INF', 'AI Inference Add-on', 'ai-ml', '{"category":"ai-ml","tier":"addon"}', 15000.00),
    ('CONS-DAY', 'Consulting Day Pack (10 days)', 'services', '{"category":"services","tier":"consulting"}', 9500.00),
    ('TRAIN-BASIC', 'Platform Training - Basic', 'training', '{"category":"training","tier":"basic"}', 3000.00)
ON CONFLICT (sku) DO NOTHING;

-- ---------------------------------------------------------------------------
-- product_supplier_prices
-- ---------------------------------------------------------------------------
INSERT INTO product_supplier_prices (product_id, supplier_name, supplier_unit_price, supplier_discount_pct)
SELECT p.id, v.supplier_name, v.supplier_unit_price, v.supplier_discount_pct
FROM (VALUES
    ('OSP-STD', 'RedCircle Distribution', 9000.00, 5.00),
    ('AAP-SUB', 'RedCircle Distribution', 6000.00, 5.00),
    ('AI-INF', 'NovaStack Supplies', 11000.00, 8.00)
) AS v(sku, supplier_name, supplier_unit_price, supplier_discount_pct)
JOIN products p ON p.sku = v.sku
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- opportunities
-- ---------------------------------------------------------------------------
INSERT INTO opportunities (reference, customer_id, primary_contact_id, name, status_id, owner_username, technical_owner_username, detected_on, due_on, budget_amount, drive_url)
SELECT v.reference, c.id, ct.id, v.name, os.id, v.owner_username, v.technical_owner_username, v.detected_on::date, v.due_on::date, v.budget_amount::numeric, v.drive_url
FROM (VALUES
    ('OPP-2026-001', 'Nimbus Cloud Works', 'alix.rennard@nimbus-cloud.example', 'Nimbus OpenShift Modernization', 'prospecting', 'a.dubois', 's.moreau', '2026-02-10', '2026-09-30', '150000.00', 'https://drive.example/aff/opp-2026-001'),
    ('OPP-2026-002', 'Solstice Robotics', 'hugo.werner@solstice-robotics.example', 'Solstice Automation Rollout', 'negotiation', 't.lemoine', 'n.bakr', '2026-01-15', '2026-07-15', '90000.00', 'https://drive.example/aff/opp-2026-002'),
    ('OPP-2026-003', 'Meridian Foodware', 'camille.ostrowski@meridian-foodware.example', 'Meridian AI Inference Pilot', 'won', 'a.dubois', 's.moreau', '2025-11-01', '2026-03-01', '60000.00', 'https://drive.example/aff/opp-2026-003'),
    ('OPP-2026-004', 'Cobalt Analytics', 'ravi.sundaram@cobalt-analytics.example', 'Cobalt Training Engagement', 'qualification', 't.lemoine', NULL, '2026-03-05', '2026-08-01', '20000.00', 'https://drive.example/aff/opp-2026-004'),
    ('OPP-2026-005', 'Fictive Aerodynamics', 'ines.castellano@fictive-aero.example', 'Fictive Platform Support Renewal', 'lost', 'l.fontaine', 'n.bakr', '2025-12-01', '2026-02-01', '40000.00', 'https://drive.example/aff/opp-2026-005')
) AS v(reference, customer_name, contact_email, name, status_code, owner_username, technical_owner_username, detected_on, due_on, budget_amount, drive_url)
JOIN customers c ON c.name = v.customer_name
JOIN contacts ct ON ct.email = v.contact_email
JOIN opportunity_statuses os ON os.code = v.status_code
ON CONFLICT (reference) DO NOTHING;

-- ---------------------------------------------------------------------------
-- quotes
-- ---------------------------------------------------------------------------
INSERT INTO quotes (reference, opportunity_id, customer_id, contact_id, status_id, owner_username, total_amount, client_po_reference, drive_url, issued_at)
SELECT v.reference, o.id, o.customer_id, o.primary_contact_id, qs.id, v.owner_username, v.total_amount::numeric, v.client_po_reference, v.drive_url, v.issued_at::timestamptz
FROM (VALUES
    ('QUO-2026-101', 'OPP-2026-001', 'accepted', 'a.dubois', '42050.00', NULL, 'https://drive.example/dev/quo-2026-101', '2026-03-01T09:00:00Z'),
    ('QUO-2026-102', 'OPP-2026-002', 'accepted', 't.lemoine', '21600.00', 'PO-SOL-4471', 'https://drive.example/dev/quo-2026-102', '2026-02-01T09:00:00Z'),
    ('QUO-2026-103', 'OPP-2026-003', 'accepted', 'a.dubois', '21000.00', 'PO-MER-9002', 'https://drive.example/dev/quo-2026-103', '2025-11-20T09:00:00Z'),
    ('QUO-2026-104', 'OPP-2026-004', 'draft', 't.lemoine', '3000.00', NULL, 'https://drive.example/dev/quo-2026-104', NULL)
) AS v(reference, opportunity_reference, status_code, owner_username, total_amount, client_po_reference, drive_url, issued_at)
JOIN opportunities o ON o.reference = v.opportunity_reference
JOIN quote_statuses qs ON qs.code = v.status_code
ON CONFLICT (reference) DO NOTHING;

-- ---------------------------------------------------------------------------
-- quote_lines
-- ---------------------------------------------------------------------------
INSERT INTO quote_lines (quote_id, product_id, sort_order, quantity, unit_price, discount_pct)
SELECT q.id, p.id, v.sort_order, v.quantity::numeric, v.unit_price::numeric, v.discount_pct::numeric
FROM (VALUES
    ('QUO-2026-101', 'OSP-PREM', 1, '1', '24000.00', '0.00'),
    ('QUO-2026-101', 'CONS-DAY', 2, '2', '9500.00', '5.00'),
    ('QUO-2026-102', 'AAP-SUB', 1, '3', '8000.00', '10.00'),
    ('QUO-2026-103', 'AI-INF', 1, '1', '15000.00', '0.00'),
    ('QUO-2026-103', 'TRAIN-BASIC', 2, '2', '3000.00', '0.00'),
    ('QUO-2026-104', 'TRAIN-BASIC', 1, '1', '3000.00', '0.00')
) AS v(quote_reference, sku, sort_order, quantity, unit_price, discount_pct)
JOIN quotes q ON q.reference = v.quote_reference
JOIN products p ON p.sku = v.sku;

-- ---------------------------------------------------------------------------
-- orders
-- ---------------------------------------------------------------------------
INSERT INTO orders (reference, quote_id, customer_id, contact_id, status_id, owner_username, sales_total_amount, supplier_total_amount, client_po_reference, drive_url, recorded_at)
SELECT v.reference, q.id, q.customer_id, q.contact_id, os.id, v.owner_username, v.sales_total_amount::numeric, v.supplier_total_amount::numeric, v.client_po_reference, v.drive_url, v.recorded_at::timestamptz
FROM (VALUES
    ('ORD-2026-201', 'QUO-2026-101', 'client_po_received', 'a.dubois', '42050.00', '31500.00', 'PO-NIM-2201', 'https://drive.example/cmd/ord-2026-201', '2026-03-10T09:00:00Z'),
    ('ORD-2026-202', 'QUO-2026-102', 'in_administration', 't.lemoine', '21600.00', '16200.00', 'PO-SOL-4471', 'https://drive.example/cmd/ord-2026-202', '2026-02-10T09:00:00Z'),
    ('ORD-2026-203', 'QUO-2026-103', 'delivered', 'a.dubois', '21000.00', '15000.00', 'PO-MER-9002', 'https://drive.example/cmd/ord-2026-203', '2025-11-25T09:00:00Z')
) AS v(reference, quote_reference, status_code, owner_username, sales_total_amount, supplier_total_amount, client_po_reference, drive_url, recorded_at)
JOIN quotes q ON q.reference = v.quote_reference
JOIN order_statuses os ON os.code = v.status_code
ON CONFLICT (reference) DO NOTHING;

-- ---------------------------------------------------------------------------
-- order_lines
-- ---------------------------------------------------------------------------
INSERT INTO order_lines (order_id, product_id, sort_order, quantity, unit_price, discount_pct, supplier_unit_price, supplier_discount_pct)
SELECT o.id, p.id, v.sort_order, v.quantity::numeric, v.unit_price::numeric, v.discount_pct::numeric, v.supplier_unit_price::numeric, v.supplier_discount_pct::numeric
FROM (VALUES
    ('ORD-2026-201', 'OSP-PREM', 1, '1', '24000.00', '0.00', '18000.00', '5.00'),
    ('ORD-2026-201', 'CONS-DAY', 2, '2', '9500.00', '5.00', '7000.00', '0.00'),
    ('ORD-2026-202', 'AAP-SUB', 1, '3', '8000.00', '10.00', '6000.00', '5.00'),
    ('ORD-2026-203', 'AI-INF', 1, '1', '15000.00', '0.00', '11000.00', '8.00'),
    ('ORD-2026-203', 'TRAIN-BASIC', 2, '2', '3000.00', '0.00', '2000.00', '0.00')
) AS v(order_reference, sku, sort_order, quantity, unit_price, discount_pct, supplier_unit_price, supplier_discount_pct)
JOIN orders o ON o.reference = v.order_reference
JOIN products p ON p.sku = v.sku;

-- ---------------------------------------------------------------------------
-- invoices
-- ---------------------------------------------------------------------------
INSERT INTO invoices (reference, order_id, customer_id, contact_id, status_id, owner_username, total_amount, invoice_type, sent_on, payment_due_on, paid_on, drive_url)
SELECT v.reference, o.id, o.customer_id, o.contact_id, i_st.id, v.owner_username, v.total_amount::numeric, v.invoice_type, v.sent_on::date, v.payment_due_on::date, v.paid_on::date, v.drive_url
FROM (VALUES
    ('INV-2026-301', 'ORD-2026-201', 'to_invoice', 'a.dubois', '42050.00', 'standard', NULL, NULL, NULL, 'https://drive.example/fac/inv-2026-301'),
    ('INV-2026-302', 'ORD-2026-202', 'sent', 't.lemoine', '21600.00', 'standard', '2026-02-20', '2026-03-20', NULL, 'https://drive.example/fac/inv-2026-302'),
    ('INV-2026-303', 'ORD-2026-203', 'paid', 'a.dubois', '21000.00', 'standard', '2025-12-01', '2025-12-31', '2025-12-28', 'https://drive.example/fac/inv-2026-303')
) AS v(reference, order_reference, status_code, owner_username, total_amount, invoice_type, sent_on, payment_due_on, paid_on, drive_url)
JOIN orders o ON o.reference = v.order_reference
JOIN invoice_statuses i_st ON i_st.code = v.status_code
ON CONFLICT (reference) DO NOTHING;

-- ---------------------------------------------------------------------------
-- invoice_lines
-- ---------------------------------------------------------------------------
INSERT INTO invoice_lines (invoice_id, product_id, sort_order, quantity, unit_price, discount_pct)
SELECT i.id, p.id, v.sort_order, v.quantity::numeric, v.unit_price::numeric, v.discount_pct::numeric
FROM (VALUES
    ('INV-2026-301', 'OSP-PREM', 1, '1', '24000.00', '0.00'),
    ('INV-2026-301', 'CONS-DAY', 2, '2', '9500.00', '5.00'),
    ('INV-2026-302', 'AAP-SUB', 1, '3', '8000.00', '10.00'),
    ('INV-2026-303', 'AI-INF', 1, '1', '15000.00', '0.00'),
    ('INV-2026-303', 'TRAIN-BASIC', 2, '2', '3000.00', '0.00')
) AS v(invoice_reference, sku, sort_order, quantity, unit_price, discount_pct)
JOIN invoices i ON i.reference = v.invoice_reference
JOIN products p ON p.sku = v.sku;

-- ---------------------------------------------------------------------------
-- activities
-- ---------------------------------------------------------------------------
INSERT INTO activities (occurred_at, activity_type, customer_id, opportunity_id, quote_id, order_id, invoice_id, actor_username, summary, related_status)
SELECT v.occurred_at::timestamptz, v.activity_type, cust.id, opp.id, quo.id, ord.id, inv.id, v.actor_username, v.summary, v.related_status
FROM (VALUES
    ('2026-03-01T10:00:00Z', 'status_change', 'Meridian Foodware', 'OPP-2026-003', NULL, NULL, NULL, 'a.dubois', 'Opportunity marked Won after quote acceptance', 'won'),
    ('2026-03-01T11:00:00Z', 'quote_sent', 'Nimbus Cloud Works', 'OPP-2026-001', 'QUO-2026-101', NULL, NULL, 'a.dubois', 'Quote sent to Nimbus Cloud Works for review', 'sent'),
    ('2026-02-12T09:30:00Z', 'order_status_change', 'Solstice Robotics', NULL, NULL, 'ORD-2026-202', NULL, 't.lemoine', 'Order moved to administration processing', 'in_administration'),
    ('2025-12-28T15:00:00Z', 'invoice_paid', 'Meridian Foodware', NULL, NULL, NULL, 'INV-2026-303', 'a.dubois', 'Invoice paid by Meridian Foodware', 'paid')
) AS v(occurred_at, activity_type, customer_name, opportunity_reference, quote_reference, order_reference, invoice_reference, actor_username, summary, related_status)
JOIN customers cust ON cust.name = v.customer_name
LEFT JOIN opportunities opp ON opp.reference = v.opportunity_reference
LEFT JOIN quotes quo ON quo.reference = v.quote_reference
LEFT JOIN orders ord ON ord.reference = v.order_reference
LEFT JOIN invoices inv ON inv.reference = v.invoice_reference;

-- ---------------------------------------------------------------------------
-- calls
-- ---------------------------------------------------------------------------
INSERT INTO calls (scheduled_at, actor_username, opportunity_id, subject, notes, is_reminder, completed_at)
SELECT v.scheduled_at::timestamptz, v.actor_username, o.id, v.subject, v.notes, v.is_reminder::boolean, v.completed_at::timestamptz
FROM (VALUES
    ('2026-02-15T14:00:00Z', 'a.dubois', 'OPP-2026-001', 'Kickoff call with Nimbus Cloud Works', 'Discussed modernization scope and timeline.', 'false', '2026-02-15T14:30:00Z'),
    ('2026-04-01T10:00:00Z', 't.lemoine', 'OPP-2026-002', 'Follow-up on Solstice negotiation', 'Reminder to confirm final pricing before month end.', 'true', NULL),
    ('2026-03-10T16:00:00Z', 'n.bakr', 'OPP-2026-004', 'Technical scoping call for Cobalt training', 'Reviewed training curriculum with Cobalt engineering team.', 'false', '2026-03-10T16:45:00Z')
) AS v(scheduled_at, actor_username, opportunity_reference, subject, notes, is_reminder, completed_at)
JOIN opportunities o ON o.reference = v.opportunity_reference;
