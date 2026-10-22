-- Estructura real de CorreoCorpAut. Ejecutar solamente en una base vacia.
-- Diez tablas de aplicacion y alembic_version (control tecnico de migraciones).
-- Sin usuarios, credenciales, correos ni datos de clientes.
-- El unico INSERT conserva la revision tecnica necesaria para arrancar la API.
BEGIN;
SET LOCAL search_path TO public;

--
-- PostgreSQL database dump
--


-- Dumped from database version 18.6
-- Dumped by pg_dump version 18.6

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: audit_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.audit_events (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid,
    actor_user_id uuid,
    mailbox_id uuid,
    action text NOT NULL,
    outcome text NOT NULL,
    request_id uuid NOT NULL,
    source text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT audit_events_action_check CHECK ((btrim(action) <> ''::text)),
    CONSTRAINT audit_events_outcome_check CHECK ((outcome = ANY (ARRAY['success'::text, 'denied'::text, 'error'::text]))),
    CONSTRAINT audit_events_source_check CHECK ((source = ANY (ARRAY['rest'::text, 'mcp'::text, 'system'::text]))),
    CONSTRAINT ck_audit_events_mailbox_tenant CHECK (((mailbox_id IS NULL) OR (tenant_id IS NOT NULL)))
);


--
-- Name: mailbox_credentials; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mailbox_credentials (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    mailbox_id uuid NOT NULL,
    username text NOT NULL,
    encrypted_secret bytea NOT NULL,
    key_version integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT mailbox_credentials_encrypted_secret_check CHECK ((octet_length(encrypted_secret) > 0)),
    CONSTRAINT mailbox_credentials_key_version_check CHECK ((key_version > 0)),
    CONSTRAINT mailbox_credentials_username_check CHECK ((btrim(username) <> ''::text))
);


--
-- Name: mailbox_grants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mailbox_grants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    mailbox_id uuid NOT NULL,
    granted_by_membership_id uuid,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: mailboxes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.mailboxes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    imap_host text NOT NULL,
    imap_port integer DEFAULT 993 NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT mailboxes_display_name_check CHECK ((btrim(display_name) <> ''::text)),
    CONSTRAINT mailboxes_email_check CHECK (((email = btrim(email)) AND (email <> ''::text))),
    CONSTRAINT mailboxes_imap_host_check CHECK (((imap_host = btrim(imap_host)) AND (imap_host <> ''::text))),
    CONSTRAINT mailboxes_imap_port_check CHECK (((imap_port >= 1) AND (imap_port <= 65535))),
    CONSTRAINT mailboxes_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'active'::text, 'disabled'::text, 'error'::text])))
);


--
-- Name: memberships; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.memberships (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    role text DEFAULT 'member'::text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT memberships_role_check CHECK ((role = ANY (ARRAY['owner'::text, 'admin'::text, 'member'::text]))),
    CONSTRAINT memberships_status_check CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))
);


--
-- Name: oauth_authorization_codes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_authorization_codes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    code_hash text NOT NULL,
    client_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    redirect_uri text NOT NULL,
    resource_uri text NOT NULL,
    scopes text[] DEFAULT ARRAY['mail:read'::text] NOT NULL,
    code_challenge text NOT NULL,
    code_challenge_method text DEFAULT 'S256'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    consumed_at timestamp with time zone,
    CONSTRAINT ck_oauth_codes_consumed CHECK (((consumed_at IS NULL) OR (consumed_at >= created_at))),
    CONSTRAINT ck_oauth_codes_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT oauth_authorization_codes_code_challenge_check CHECK ((code_challenge ~ '^[A-Za-z0-9_-]{43}$'::text)),
    CONSTRAINT oauth_authorization_codes_code_challenge_method_check CHECK ((code_challenge_method = 'S256'::text)),
    CONSTRAINT oauth_authorization_codes_code_hash_check CHECK ((code_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT oauth_authorization_codes_redirect_uri_check CHECK ((btrim(redirect_uri) <> ''::text)),
    CONSTRAINT oauth_authorization_codes_resource_uri_check CHECK ((btrim(resource_uri) <> ''::text)),
    CONSTRAINT oauth_authorization_codes_scopes_check CHECK ((scopes = ARRAY['mail:read'::text]))
);


--
-- Name: oauth_clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_clients (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    client_id text NOT NULL,
    name text NOT NULL,
    client_secret_hash text,
    redirect_uris text[] NOT NULL,
    token_endpoint_auth_method text DEFAULT 'none'::text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT ck_oauth_clients_redirect_uris CHECK (((cardinality(redirect_uris) > 0) AND (array_position(redirect_uris, NULL::text) IS NULL) AND (NOT (''::text = ANY (redirect_uris))))),
    CONSTRAINT ck_oauth_clients_secret CHECK ((((token_endpoint_auth_method = 'none'::text) AND (client_secret_hash IS NULL)) OR ((token_endpoint_auth_method = 'client_secret_basic'::text) AND (client_secret_hash IS NOT NULL) AND (btrim(client_secret_hash) <> ''::text)))),
    CONSTRAINT oauth_clients_client_id_check CHECK ((btrim(client_id) <> ''::text)),
    CONSTRAINT oauth_clients_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT oauth_clients_status_check CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text]))),
    CONSTRAINT oauth_clients_token_endpoint_auth_method_check CHECK ((token_endpoint_auth_method = ANY (ARRAY['none'::text, 'client_secret_basic'::text])))
);


--
-- Name: oauth_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.oauth_tokens (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    token_hash text NOT NULL,
    token_type text NOT NULL,
    grant_id uuid NOT NULL,
    client_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    membership_id uuid NOT NULL,
    resource_uri text NOT NULL,
    scopes text[] DEFAULT ARRAY['mail:read'::text] NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT ck_oauth_tokens_expiry CHECK ((expires_at > created_at)),
    CONSTRAINT ck_oauth_tokens_revocation CHECK (((revoked_at IS NULL) OR (revoked_at >= created_at))),
    CONSTRAINT oauth_tokens_resource_uri_check CHECK ((btrim(resource_uri) <> ''::text)),
    CONSTRAINT oauth_tokens_scopes_check CHECK ((scopes = ARRAY['mail:read'::text])),
    CONSTRAINT oauth_tokens_token_hash_check CHECK ((token_hash ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT oauth_tokens_token_type_check CHECK ((token_type = ANY (ARRAY['access'::text, 'refresh'::text])))
);


--
-- Name: tenants; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tenants (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT tenants_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT tenants_slug_check CHECK ((slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'::text)),
    CONSTRAINT tenants_status_check CHECK ((status = ANY (ARRAY['active'::text, 'suspended'::text, 'disabled'::text])))
);


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text,
    password_hash text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    is_platform_admin boolean DEFAULT false NOT NULL,
    username text,
    CONSTRAINT ck_users_login_identifier CHECK (((email IS NOT NULL) OR (username IS NOT NULL))),
    CONSTRAINT ck_users_username_format CHECK (((username IS NULL) OR (username ~ '^[a-z][a-z0-9_.-]{2,31}$'::text))),
    CONSTRAINT users_email_check CHECK (((email = btrim(email)) AND (email <> ''::text))),
    CONSTRAINT users_name_check CHECK ((btrim(name) <> ''::text)),
    CONSTRAINT users_password_hash_check CHECK ((btrim(password_hash) <> ''::text)),
    CONSTRAINT users_status_check CHECK ((status = ANY (ARRAY['active'::text, 'disabled'::text])))
);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_events audit_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_pkey PRIMARY KEY (id);


--
-- Name: mailbox_credentials mailbox_credentials_mailbox_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_credentials
    ADD CONSTRAINT mailbox_credentials_mailbox_id_key UNIQUE (mailbox_id);


--
-- Name: mailbox_credentials mailbox_credentials_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_credentials
    ADD CONSTRAINT mailbox_credentials_pkey PRIMARY KEY (id);


--
-- Name: mailbox_grants mailbox_grants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT mailbox_grants_pkey PRIMARY KEY (id);


--
-- Name: mailboxes mailboxes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailboxes
    ADD CONSTRAINT mailboxes_pkey PRIMARY KEY (id);


--
-- Name: memberships memberships_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_pkey PRIMARY KEY (id);


--
-- Name: oauth_authorization_codes oauth_authorization_codes_code_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_code_hash_key UNIQUE (code_hash);


--
-- Name: oauth_authorization_codes oauth_authorization_codes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_pkey PRIMARY KEY (id);


--
-- Name: oauth_clients oauth_clients_client_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_client_id_key UNIQUE (client_id);


--
-- Name: oauth_clients oauth_clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_clients
    ADD CONSTRAINT oauth_clients_pkey PRIMARY KEY (id);


--
-- Name: oauth_tokens oauth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_pkey PRIMARY KEY (id);


--
-- Name: oauth_tokens oauth_tokens_token_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_token_hash_key UNIQUE (token_hash);


--
-- Name: tenants tenants_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--
-- Name: tenants tenants_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_slug_key UNIQUE (slug);


--
-- Name: mailbox_grants uq_mailbox_grants_membership_mailbox; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT uq_mailbox_grants_membership_mailbox UNIQUE (membership_id, mailbox_id);


--
-- Name: mailboxes uq_mailboxes_tenant_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailboxes
    ADD CONSTRAINT uq_mailboxes_tenant_id UNIQUE (tenant_id, id);


--
-- Name: memberships uq_memberships_tenant_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT uq_memberships_tenant_id UNIQUE (tenant_id, id);


--
-- Name: memberships uq_memberships_tenant_user; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT uq_memberships_tenant_user UNIQUE (tenant_id, user_id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: ix_audit_events_actor_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_actor_created_at ON public.audit_events USING btree (actor_user_id, created_at DESC);


--
-- Name: ix_audit_events_request_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_request_id ON public.audit_events USING btree (request_id);


--
-- Name: ix_audit_events_tenant_created_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_tenant_created_at ON public.audit_events USING btree (tenant_id, created_at DESC);


--
-- Name: ix_audit_events_tenant_mailbox; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_audit_events_tenant_mailbox ON public.audit_events USING btree (tenant_id, mailbox_id);


--
-- Name: ix_mailbox_grants_tenant_grantor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mailbox_grants_tenant_grantor ON public.mailbox_grants USING btree (tenant_id, granted_by_membership_id);


--
-- Name: ix_mailbox_grants_tenant_mailbox; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_mailbox_grants_tenant_mailbox ON public.mailbox_grants USING btree (tenant_id, mailbox_id);


--
-- Name: ix_memberships_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_memberships_user_id ON public.memberships USING btree (user_id);


--
-- Name: ix_oauth_codes_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_codes_client_id ON public.oauth_authorization_codes USING btree (client_id);


--
-- Name: ix_oauth_codes_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_codes_expires_at ON public.oauth_authorization_codes USING btree (expires_at);


--
-- Name: ix_oauth_codes_tenant_membership; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_codes_tenant_membership ON public.oauth_authorization_codes USING btree (tenant_id, membership_id);


--
-- Name: ix_oauth_tokens_client_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_tokens_client_id ON public.oauth_tokens USING btree (client_id);


--
-- Name: ix_oauth_tokens_expires_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_tokens_expires_at ON public.oauth_tokens USING btree (expires_at);


--
-- Name: ix_oauth_tokens_grant_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_tokens_grant_id ON public.oauth_tokens USING btree (grant_id);


--
-- Name: ix_oauth_tokens_tenant_membership; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_oauth_tokens_tenant_membership ON public.oauth_tokens USING btree (tenant_id, membership_id);


--
-- Name: uq_mailboxes_tenant_email_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_mailboxes_tenant_email_normalized ON public.mailboxes USING btree (tenant_id, lower(email));


--
-- Name: uq_users_email_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_email_normalized ON public.users USING btree (lower(email));


--
-- Name: uq_users_single_platform_admin; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_single_platform_admin ON public.users USING btree (is_platform_admin) WHERE (is_platform_admin IS TRUE);


--
-- Name: uq_users_username_normalized; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_users_username_normalized ON public.users USING btree (lower(username));


--
-- Name: audit_events audit_events_actor_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_actor_user_id_fkey FOREIGN KEY (actor_user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: audit_events audit_events_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT audit_events_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: audit_events fk_audit_events_mailbox; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.audit_events
    ADD CONSTRAINT fk_audit_events_mailbox FOREIGN KEY (tenant_id, mailbox_id) REFERENCES public.mailboxes(tenant_id, id) ON DELETE CASCADE;


--
-- Name: mailbox_grants fk_mailbox_grants_grantor; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT fk_mailbox_grants_grantor FOREIGN KEY (tenant_id, granted_by_membership_id) REFERENCES public.memberships(tenant_id, id) ON DELETE CASCADE;


--
-- Name: mailbox_grants fk_mailbox_grants_mailbox; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT fk_mailbox_grants_mailbox FOREIGN KEY (tenant_id, mailbox_id) REFERENCES public.mailboxes(tenant_id, id) ON DELETE CASCADE;


--
-- Name: mailbox_grants fk_mailbox_grants_membership; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT fk_mailbox_grants_membership FOREIGN KEY (tenant_id, membership_id) REFERENCES public.memberships(tenant_id, id) ON DELETE CASCADE;


--
-- Name: oauth_authorization_codes fk_oauth_codes_membership; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT fk_oauth_codes_membership FOREIGN KEY (tenant_id, membership_id) REFERENCES public.memberships(tenant_id, id) ON DELETE CASCADE;


--
-- Name: oauth_tokens fk_oauth_tokens_membership; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT fk_oauth_tokens_membership FOREIGN KEY (tenant_id, membership_id) REFERENCES public.memberships(tenant_id, id) ON DELETE CASCADE;


--
-- Name: mailbox_credentials mailbox_credentials_mailbox_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_credentials
    ADD CONSTRAINT mailbox_credentials_mailbox_id_fkey FOREIGN KEY (mailbox_id) REFERENCES public.mailboxes(id) ON DELETE CASCADE;


--
-- Name: mailbox_grants mailbox_grants_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailbox_grants
    ADD CONSTRAINT mailbox_grants_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: mailboxes mailboxes_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.mailboxes
    ADD CONSTRAINT mailboxes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: memberships memberships_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.memberships
    ADD CONSTRAINT memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE RESTRICT;


--
-- Name: oauth_authorization_codes oauth_authorization_codes_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(id) ON DELETE RESTRICT;


--
-- Name: oauth_authorization_codes oauth_authorization_codes_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_authorization_codes
    ADD CONSTRAINT oauth_authorization_codes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- Name: oauth_tokens oauth_tokens_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.oauth_clients(id) ON DELETE RESTRICT;


--
-- Name: oauth_tokens oauth_tokens_tenant_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.oauth_tokens
    ADD CONSTRAINT oauth_tokens_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

-- Comentarios tecnicos del esquema real.
COMMENT ON TABLE public.audit_events IS 'Eventos sin cuerpos, asuntos, adjuntos, terminos de busqueda, tokens ni credenciales.';
COMMENT ON COLUMN public.mailbox_credentials.encrypted_secret IS 'Sobre cifrado autenticado generado por la aplicacion; debe incluir nonce y tag. Nunca texto plano.';
COMMENT ON COLUMN public.mailbox_credentials.key_version IS 'Referencia a una clave externa a PostgreSQL; permite rotar las credenciales.';
COMMENT ON TABLE public.mailbox_grants IS 'Todos los permisos son de lectura. Revocar elimina la concesion y genera un evento de auditoria.';
COMMENT ON TABLE public.mailboxes IS 'Configuracion IMAP exclusivamente con TLS y validacion de certificado. No almacena mensajes.';
COMMENT ON TABLE public.oauth_tokens IS 'Una fila por token opaco. grant_id agrupa access/refresh y sus rotaciones para revocacion conjunta.';

INSERT INTO public.alembic_version (version_num) VALUES ('20261021_0004');
COMMIT;
