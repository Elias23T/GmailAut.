-- Restricciones OAuth del esquema completo seeder/01_schema.sql.
BEGIN;
DO $$
DECLARE
    user_a UUID;
    user_b UUID;
    tenant_a UUID;
    tenant_b UUID;
    member_a UUID;
    member_b UUID;
    client UUID;
BEGIN
    INSERT INTO users (email, password_hash, name)
        VALUES ('oauth-a@example.invalid', 'test-hash', 'A') RETURNING id INTO user_a;
    INSERT INTO users (email, password_hash, name)
        VALUES ('oauth-b@example.invalid', 'test-hash', 'B') RETURNING id INTO user_b;
    INSERT INTO tenants (name, slug) VALUES ('OAuth A', 'oauth-test-a') RETURNING id INTO tenant_a;
    INSERT INTO tenants (name, slug) VALUES ('OAuth B', 'oauth-test-b') RETURNING id INTO tenant_b;
    INSERT INTO memberships (tenant_id, user_id)
        VALUES (tenant_a, user_a) RETURNING id INTO member_a;
    INSERT INTO memberships (tenant_id, user_id)
        VALUES (tenant_b, user_b) RETURNING id INTO member_b;
    INSERT INTO oauth_clients (client_id, name, redirect_uris)
        VALUES ('schema-test-client', 'Test', ARRAY['https://example.invalid/callback']) RETURNING id INTO client;
    -- Flujo valido: codigo y tokens vinculados a una membresia y recurso.
    INSERT INTO oauth_authorization_codes (
        code_hash, client_id, tenant_id, membership_id, redirect_uri,
        resource_uri, code_challenge, expires_at
    ) VALUES (
        repeat('a', 64), client, tenant_a, member_a, 'https://example.invalid/callback',
        'https://example.invalid/mcp', repeat('a', 43), CURRENT_TIMESTAMP + INTERVAL '5 minutes'
    );
    INSERT INTO oauth_tokens (
        token_hash, token_type, grant_id, client_id, tenant_id, membership_id, resource_uri, expires_at
    ) VALUES (
        repeat('b', 64), 'access', gen_random_uuid(), client, tenant_a, member_a,
        'https://example.invalid/mcp', CURRENT_TIMESTAMP + INTERVAL '10 minutes'
    );
    BEGIN
        INSERT INTO oauth_tokens (
            token_hash, token_type, grant_id, client_id, tenant_id, membership_id, resource_uri, expires_at
        ) VALUES (
            repeat('c', 64), 'access', gen_random_uuid(), client, tenant_a, member_b,
            'https://example.invalid/mcp', CURRENT_TIMESTAMP + INTERVAL '10 minutes'
        );
        RAISE EXCEPTION 'FALLO: se permitio un token con membresia de otra empresa';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO oauth_tokens (
            token_hash, token_type, grant_id, client_id, tenant_id, membership_id, resource_uri, expires_at
        ) VALUES (
            repeat('c', 64), 'refresh', gen_random_uuid(), client, tenant_a, member_a,
            'https://example.invalid/mcp', CURRENT_TIMESTAMP - INTERVAL '1 minute'
        );
        RAISE EXCEPTION 'FALLO: se permitio una expiracion anterior a la emision';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        UPDATE oauth_tokens SET scopes = ARRAY['mail:write'] WHERE client_id = client;
        RAISE EXCEPTION 'FALLO: se permitio un alcance de escritura';
    EXCEPTION WHEN check_violation THEN NULL;
    END;


    IF NOT has_table_privilege('corporate_mail_app', 'oauth_tokens', 'INSERT') THEN
        RAISE EXCEPTION 'FALLO: faltan permisos para el esquema OAuth opcional';
    END IF;
    UPDATE oauth_tokens SET scopes = ARRAY['mail:read','mail:send'] WHERE client_id = client;
    RAISE NOTICE 'OK: esquema OAuth y alcances de lectura con envio opcional';
END;
$$;
ROLLBACK;
