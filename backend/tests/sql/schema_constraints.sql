-- Ejecutar sobre el esquema completo de prueba; validate_schema.py prepara el rol limitado.
-- Todas las filas se revierten; ejecutar como administrador con permiso de SET ROLE.
BEGIN;

DO $$
DECLARE
    user_a UUID;
    user_b UUID;
    tenant_a UUID;
    tenant_b UUID;
    member_a UUID;
    member_b UUID;
    mailbox_a UUID;
    mailbox_b UUID;
BEGIN
    INSERT INTO users (email, password_hash, name)
        VALUES ('schema-a@example.invalid', 'test-hash-not-a-real-password', 'A') RETURNING id INTO user_a;
    INSERT INTO users (email, password_hash, name)
        VALUES ('schema-b@example.invalid', 'test-hash-not-a-real-password', 'B') RETURNING id INTO user_b;
    INSERT INTO tenants (name, slug) VALUES ('Schema A', 'schema-test-a') RETURNING id INTO tenant_a;
    INSERT INTO tenants (name, slug) VALUES ('Schema B', 'schema-test-b') RETURNING id INTO tenant_b;
    INSERT INTO memberships (tenant_id, user_id, role)
        VALUES (tenant_a, user_a, 'owner') RETURNING id INTO member_a;
    INSERT INTO memberships (tenant_id, user_id, role)
        VALUES (tenant_b, user_b, 'owner') RETURNING id INTO member_b;
    -- La misma persona puede pertenecer a otra empresa.
    INSERT INTO memberships (tenant_id, user_id) VALUES (tenant_b, user_a);
    INSERT INTO mailboxes (tenant_id, email, display_name, imap_host)
        VALUES (tenant_a, 'mail@example.invalid', 'A', 'imap.example.invalid') RETURNING id INTO mailbox_a;
    INSERT INTO mailboxes (tenant_id, email, display_name, imap_host)
        VALUES (tenant_b, 'mail@example.invalid', 'B', 'imap.example.invalid') RETURNING id INTO mailbox_b;
    INSERT INTO mailbox_grants (tenant_id, membership_id, mailbox_id, granted_by_membership_id)
        VALUES (tenant_a, member_a, mailbox_a, member_a);

    BEGIN
        INSERT INTO mailbox_grants (tenant_id, membership_id, mailbox_id)
            VALUES (tenant_a, member_a, mailbox_b);
        RAISE EXCEPTION 'FALLO: se permitio un buzon de otra empresa';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO mailbox_grants (tenant_id, membership_id, mailbox_id)
            VALUES (tenant_a, member_b, mailbox_a);
        RAISE EXCEPTION 'FALLO: se permitio una membresia de otra empresa';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        UPDATE mailbox_grants SET granted_by_membership_id = member_b WHERE mailbox_id = mailbox_a;
        RAISE EXCEPTION 'FALLO: se permitio un otorgante de otra empresa';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO mailbox_grants (tenant_id, membership_id, mailbox_id)
            VALUES (tenant_a, member_a, mailbox_a);
        RAISE EXCEPTION 'FALLO: se permitio un permiso duplicado';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO memberships (tenant_id, user_id) VALUES (tenant_a, user_a);
        RAISE EXCEPTION 'FALLO: se permitio una membresia duplicada';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO users (email, password_hash, name)
            VALUES ('SCHEMA-A@example.invalid', 'test-hash', 'Duplicado');
        RAISE EXCEPTION 'FALLO: email de usuario duplicado por mayusculas';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO mailboxes (tenant_id, email, display_name, imap_host)
            VALUES (tenant_a, 'MAIL@example.invalid', 'Duplicado', 'imap.example.invalid');
        RAISE EXCEPTION 'FALLO: email de buzon duplicado dentro de una empresa';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO mailbox_credentials (mailbox_id, username, encrypted_secret, key_version)
            VALUES (mailbox_a, 'mail@example.invalid', decode('', 'hex'), 1);
        RAISE EXCEPTION 'FALLO: se permitio una credencial vacia';
    EXCEPTION WHEN check_violation THEN NULL;
    END;

    INSERT INTO audit_events (tenant_id, actor_user_id, mailbox_id, action, outcome, request_id, source)
        VALUES (tenant_a, user_a, mailbox_a, 'mailbox.read', 'success', gen_random_uuid(), 'rest');
    BEGIN
        INSERT INTO audit_events (tenant_id, mailbox_id, action, outcome, request_id, source)
            VALUES (tenant_a, mailbox_b, 'mailbox.read', 'denied', gen_random_uuid(), 'mcp');
        RAISE EXCEPTION 'FALLO: auditoria de buzon con empresa incorrecta';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    IF NOT has_table_privilege('corporate_mail_app', 'audit_events', 'INSERT')
        OR has_table_privilege('corporate_mail_app', 'audit_events', 'UPDATE')
        OR has_table_privilege('corporate_mail_app', 'audit_events', 'DELETE')
        OR has_table_privilege('corporate_mail_app', 'audit_events', 'TRUNCATE')
        OR has_schema_privilege('corporate_mail_app', 'public', 'CREATE') THEN
        RAISE EXCEPTION 'FALLO: privilegios incorrectos para el rol de aplicacion';
    END IF;

    RAISE NOTICE 'OK: integridad multiempresa, unicidad y privilegios de auditoria';
END;
$$;

-- Verificar las operaciones con los permisos reales del usuario de aplicacion.
SET LOCAL ROLE corporate_mail_app;
DO $$
BEGIN
    BEGIN
        UPDATE audit_events SET outcome = 'error' WHERE FALSE;
        RAISE EXCEPTION 'FALLO: se permitio modificar la auditoria';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        DELETE FROM audit_events WHERE FALSE;
        RAISE EXCEPTION 'FALLO: se permitio eliminar la auditoria';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    BEGIN
        EXECUTE 'TRUNCATE audit_events';
        RAISE EXCEPTION 'FALLO: se permitio truncar la auditoria';
    EXCEPTION WHEN insufficient_privilege THEN NULL;
    END;
    RAISE NOTICE 'OK: el rol de aplicacion no modifica, elimina ni trunca auditoria';
END;
$$;

ROLLBACK;
