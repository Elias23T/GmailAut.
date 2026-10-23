# Corporate Mail AI en AlmaLinux

Guía para una VPS nueva con **AlmaLinux 9 actualizado, x86_64**, PostgreSQL 18,
Python 3.12, Node.js 22, Caddy y systemd. No utiliza Docker, Vite como servidor
de producción ni Ngrok. AlmaLinux 10 tiene otros paquetes y no es el destino
de los comandos de instalación de esta guía.

La configuración está preparada en el repositorio. La instalación efectiva,
SELinux, certificados y conexión desde ChatGPT deben verificarse en la VPS.

## Entrega al responsable de despliegue

Publica en Git todo el código y los archivos nuevos, incluidas las migraciones,
`deploy/`, `scripts/` y esta guía. No publiques archivos de entorno ni dumps.
La clave de cifrado anterior solo se entrega por un canal privado si se
traslada la base actual. No es necesaria para una instalación vacía.

Revisa el contenido antes de crear el commit desde la raíz del repositorio:

```bash
git status --short
git add .
git diff --cached --stat
git commit -m "Prepare Corporate Mail AI for native VPS deployment"
git push origin main
```

Tu compañero debe clonar ese commit y utilizar el subdominio definitivo.
Los archivos de texto se normalizan a LF mediante `.gitattributes`.
No debe copiar las URLs de Ngrok ni tus entornos locales al servidor.

## 1. Requisitos

| Recurso | Requisito |
|---|---|
| VPS | Punto de partida: 2 vCPU, 2 GB RAM, 20 GB SSD; ajustar según concurrencia |
| Acceso | SSH y un usuario con sudo |
| Dominio | Un subdominio propio, por ejemplo `correo.example.com` |
| DNS | Registro A a la IPv4 de la VPS; AAAA solo si IPv6 funciona |
| Python | 3.12 o superior; se usa `python3.12` sin modificar el Python del sistema |
| Node.js | 22.12 o superior, solo para compilar el frontend |
| PostgreSQL | 18, escuchando únicamente en localhost |
| Entrada | TCP 80 y 443; SSH según tu configuración |
| Salida | DNS, HTTPS y los puertos IMAP/SMTP de tus proveedores: normalmente 993, 465 o 587 |
| Correo | Buzón real y credenciales válidas; TLS con certificado válido |
| ChatGPT | Una cuenta que permita configurar un servidor MCP personalizado |

La memoria indicada es una estimación inicial, no una prueba de carga.
Consulta al proveedor de VPS si bloquea SMTP saliente: abrir puertos entrantes
en firewalld no elimina una restricción de salida del proveedor.

Todos los nombres de dominio de esta guía son ejemplos. Sustituye
`correo.example.com` por tu dominio real. La base se llama `CorreoCorpAut`.

## 2. Instalar paquetes

En una VPS nueva:

```bash
sudo dnf upgrade -y
sudo dnf install -y git rsync curl openssl ca-certificates firewalld \
  dnf-plugins-core policycoreutils-python-utils python3.12 python3.12-pip
sudo dnf module enable -y nodejs:22
sudo dnf install -y nodejs npm
python3.12 --version
node --version
npm --version
```

Node debe cumplir `>=22.12.0`. AlmaLinux ofrece Node.js 22 en AppStream y
paquetes de Python 3.12. [AlmaLinux 9.6](https://wiki.almalinux.org/release-notes/9.6.html),
[paquetes Python](https://errata.almalinux.org/9/ALSA-2024-6146.html).

Instala PostgreSQL 18 desde PGDG para EL9 x86_64:

```bash
sudo dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm
sudo dnf -qy module disable postgresql
sudo dnf install -y postgresql18-server postgresql18
sudo /usr/pgsql-18/bin/postgresql-18-setup initdb
sudo systemctl enable --now postgresql-18
```

`initdb` se ejecuta **solo si el servidor PostgreSQL es nuevo y está vacío**.
Para otra arquitectura usa el selector del [repositorio oficial PostgreSQL](https://www.postgresql.org/download/linux/redhat/).

Instala Caddy con el repositorio indicado por el proyecto:

```bash
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy
```

Fuente: [instalación oficial de Caddy para Red Hat](https://caddyserver.com/docs/install#fedora-redhat-centos).

## 3. Crear roles y base de datos

Usa un rol propietario para migraciones y otro limitado para la API. Las
contraseñas PostgreSQL son independientes de las cuentas del panel y del correo.

```bash
sudo -u postgres /usr/pgsql-18/bin/psql
```

Dentro de psql, solo en una instalación nueva:

```sql
CREATE ROLE corporate_mail_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\password corporate_mail_owner
CREATE ROLE corporate_mail_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
\password corporate_mail_app
CREATE DATABASE "CorreoCorpAut" OWNER corporate_mail_owner ENCODING 'UTF8' TEMPLATE template0;
REVOKE ALL ON DATABASE "CorreoCorpAut" FROM PUBLIC;
GRANT CONNECT ON DATABASE "CorreoCorpAut" TO corporate_mail_app;
\connect CorreoCorpAut
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO corporate_mail_app;
\q
```

En `/var/lib/pgsql/18/data/postgresql.conf`, configura:

```conf
listen_addresses = '127.0.0.1'
password_encryption = 'scram-sha-256'
```

En `/var/lib/pgsql/18/data/pg_hba.conf`, coloca estas reglas **antes de reglas
host más generales**; conserva el acceso local del usuario postgres:

```conf
host  CorreoCorpAut  corporate_mail_owner  127.0.0.1/32  scram-sha-256
host  CorreoCorpAut  corporate_mail_app    127.0.0.1/32  scram-sha-256
```

```bash
sudo systemctl restart postgresql-18
```

No publiques 5432 en el firewall. Si ya existe PostgreSQL, adapta roles y base
sin repetir `CREATE DATABASE`, `CREATE ROLE` o `initdb`.

## 4. Instalar el proyecto

Ejecuta como tu usuario de despliegue con sudo, no como la cuenta del servicio:

```bash
sudo useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /sbin/nologin corporate-mail-ai
sudo install -d -o "$(id -un)" -g "$(id -gn)" -m 0755 /opt/corporate-mail-ai
git clone https://github.com/Elias23T/GmailAut..git /opt/corporate-mail-ai
cd /opt/corporate-mail-ai
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install ./backend
backend/.venv/bin/python -m pip check
```

El repositorio debe contener estos cambios antes de clonarlo. La preparación
local no publica automáticamente un commit en GitHub. No copies `.venv`,
`node_modules` ni los archivos `.env` de Windows como instalación del servidor.

## 5. Crear la configuración de producción

```bash
sudo install -d -o root -g corporate-mail-ai -m 0750 /etc/corporate-mail-ai
sudo /opt/corporate-mail-ai/backend/.venv/bin/python \
  /opt/corporate-mail-ai/scripts/configure_production.py \
  --output /etc/corporate-mail-ai/backend.env \
  --origin https://correo.example.com
sudo chown root:corporate-mail-ai /etc/corporate-mail-ai/backend.env
sudo chmod 0640 /etc/corporate-mail-ai/backend.env
sudo ln -s /etc/corporate-mail-ai/backend.env /opt/corporate-mail-ai/backend/.env
```

Introduce la contraseña PostgreSQL de `corporate_mail_app` cuando se solicite.
El script codifica los caracteres especiales de la contraseña en la URL,
genera JWT y clave de cifrado, y crea el archivo sin mostrar secretos.
Se niega a sobrescribir archivos existentes. El enlace `.env` permite usar
también los comandos administrativos desde `backend/`.

Si **trasladas la base actual con buzones cifrados**, conserva su clave anterior.
Agrega a la creación del entorno:

```bash
--reuse-encryption-key-file /ruta/protegida/entorno-anterior.env
```

Guarda ese archivo anterior de forma privada. Una clave nueva no puede
descifrar las contraseñas de buzones de una base importada. El JWT nuevo
requiere volver a iniciar sesión. No ejecutes el generador después para
reemplazar claves que ya están en uso.

Variables principales del archivo generado:

| Variable | Valor |
|---|---|
| `APP_ENV` | `production` |
| `PUBLIC_BASE_URL`, `FRONTEND_URL` | El mismo origen `https://correo.example.com`, sin `/mcp` |
| `DATABASE_URL` | Rol limitado y base `CorreoCorpAut` en localhost |
| `CORS_ORIGINS` | JSON con el origen público |
| `OAUTH_REDIRECT_URIS` | JSON con el callback exacto de la configuración MCP en ChatGPT |
| `JWT_SECRET` | Generado; mínimo 32 caracteres |
| `MAILBOX_ENCRYPTION_KEY` | Generada o conservada al trasladar datos |
| `MAILBOX_ENCRYPTION_KEY_VERSION` | Versión correspondiente a esa clave |
| `IMAP_ALLOW_PRIVATE_HOSTS`, `SMTP_ALLOW_PRIVATE_HOSTS` | `false` |

El callback predeterminado es `https://chatgpt.com/connector_platform_oauth_redirect`.
Si ChatGPT muestra otro, pasa `--callback URL_EXACTA` al generador o edita
`OAUTH_REDIRECT_URIS` con `sudoedit`. No uses comodines. Ningún secreto debe
llevar prefijo `VITE_`: esas variables se incluyen en el JavaScript público.

Configura **solo para las migraciones**:

```bash
sudo install -o root -g root -m 0600 /dev/null /etc/corporate-mail-ai/migrations.env
sudoedit /etc/corporate-mail-ai/migrations.env
```

Contenido, sustituyendo la contraseña del rol propietario:

```dotenv
MIGRATION_DATABASE_URL=postgresql+psycopg://corporate_mail_owner:CONTRASENA_CODIFICADA@127.0.0.1:5432/CorreoCorpAut
```

Los caracteres especiales de esa contraseña deben estar codificados para URL
(`@` → `%40`, `#` → `%23`, etc.). Usa una contraseña aleatoria URL-safe o
codifícala con `urllib.parse.quote(password, safe='')` sin imprimirla.
La API no carga este archivo; systemd lo entrega únicamente al proceso de migración.

## 6. Migraciones y permisos SQL

```bash
cd /opt/corporate-mail-ai
sudo cp deploy/systemd/corporate-mail-ai.service.example /etc/systemd/system/corporate-mail-ai.service
sudo cp deploy/systemd/corporate-mail-ai-migrate.service.example /etc/systemd/system/corporate-mail-ai-migrate.service
sudo chgrp -hR corporate-mail-ai /opt/corporate-mail-ai
sudo chmod -R g-w,o-rwx /opt/corporate-mail-ai
sudo systemctl daemon-reload
sudo systemctl start corporate-mail-ai-migrate
sudo journalctl -u corporate-mail-ai-migrate -n 30 --no-pager
```

La revisión actual es `20261023_0008`: 11 tablas de aplicación y
`alembic_version` (12 en total). **No ejecutes además `seeder/01_schema.sql`**
sobre una base instalada con Alembic. El servicio de migración se inicia a
mano y no se habilita para cada arranque.

Después de migrar, asigna permisos al rol de ejecución:

```bash
sudo -u postgres /usr/pgsql-18/bin/psql -d CorreoCorpAut
```

```sql
GRANT USAGE ON SCHEMA public TO corporate_mail_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  users, tenants, memberships, mailboxes, mailbox_credentials, mailbox_grants,
  oauth_clients, oauth_authorization_codes, oauth_tokens, outgoing_messages
  TO corporate_mail_app;
REVOKE ALL ON audit_events FROM corporate_mail_app;
GRANT SELECT, INSERT ON audit_events TO corporate_mail_app;
GRANT SELECT ON alembic_version TO corporate_mail_app;
\q
```

El rol de la API no es propietario de las tablas y no puede modificar,
borrar ni truncar auditoría. Revisa estos permisos tras migraciones que creen
nuevas tablas. No hace falta agregar triggers ni más SQL al seeder.

## 7. Compilar y publicar el frontend

```bash
cd /opt/corporate-mail-ai/frontend
VITE_API_BASE_URL=/api npm ci
VITE_API_BASE_URL=/api npm run build
sudo install -d -m 0755 /var/www/corporate-mail-ai
sudo rsync -a --delete dist/ /var/www/corporate-mail-ai/
sudo chown -R root:root /var/www/corporate-mail-ai
sudo find /var/www/corporate-mail-ai -type d -exec chmod 0755 {} \;
sudo find /var/www/corporate-mail-ai -type f -exec chmod 0644 {} \;
```

`--delete` sincroniza únicamente el directorio dedicado `/var/www/corporate-mail-ai/`.
No apuntes este comando a otro directorio. Caddy solo sirve estos archivos,
no el backend, el repositorio ni los secretos. No necesitas mantener Node
o `npm run dev` ejecutándose.

## 8. Caddy, HTTPS, SELinux y firewall

```bash
cd /opt/corporate-mail-ai
sudo cp deploy/caddy/Caddyfile.example /etc/caddy/Caddyfile
sudoedit /etc/caddy/Caddyfile
```

Cambia `mail.example.com` por el mismo dominio de `PUBLIC_BASE_URL`.
Si esta VPS ya sirve otros sitios, incorpora el bloque sin reemplazar sus
configuraciones. Las rutas quedan así:

| Ruta pública | Destino |
|---|---|
| `/` y `/connect` | Frontend compilado |
| `/api/*` | FastAPI, quitando el prefijo `/api` |
| `/mcp`, `/oauth/*`, `/.well-known/*` | FastAPI, conservando la ruta |

Mantén SELinux activo y etiqueta los archivos estáticos:

```bash
sudo semanage fcontext -a -t httpd_sys_content_t '/var/www/corporate-mail-ai(/.*)?'
sudo restorecon -Rv /var/www/corporate-mail-ai
sudo setsebool -P httpd_can_network_connect on
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl enable --now corporate-mail-ai
sudo systemctl enable --now caddy
```

Si el contexto ya existe, usa `semanage fcontext -m` en lugar de `-a`.
Conserva la regla correspondiente si tu SSH utiliza un puerto personalizado.
Abre también 80/443 en el firewall del proveedor. No abras 8000, 5173 ni 5432
al exterior. El paquete COPR prepara Caddy para systemd y SELinux; consulta
[las instrucciones oficiales](https://caddyserver.com/docs/running#selinux-considerations).

Caddy solicita y renueva el certificado automáticamente si el dominio resuelve
a esta VPS y los puertos requeridos están accesibles. Conserva `/var/lib/caddy`
entre reinicios. Consulta [HTTPS automático](https://caddyserver.com/docs/automatic-https).

## 9. Administrador y comprobación

Desde `backend/`, con el entorno enlazado en el paso 5:

```bash
cd /opt/corporate-mail-ai/backend
sudo -u corporate-mail-ai .venv/bin/python -m app.cli create-admin --username admin01 --name "Administrador"
curl --fail http://127.0.0.1:8000/health/ready
curl --fail https://correo.example.com/api/health/ready
curl --fail https://correo.example.com/.well-known/oauth-protected-resource/mcp
curl -i https://correo.example.com/mcp
```

La contraseña del administrador se solicita sin mostrarla. Si importaste una
base con administradores existentes, entra con esas cuentas; no las dupliques.

Resultados esperados: disponibilidad `200` con `database: ok`; metadata OAuth
con el dominio real; `/mcp` sin credenciales devuelve **401**, no 200, con
`WWW-Authenticate` y `scope="mail:read mail:send"`.

Prueba manual antes de dar acceso a clientes:

1. Abre el dominio e inicia sesión como administrador.
2. Crea una empresa y un cliente con credenciales propias.
3. Configura un buzón real: Incoming Server, IMAP Port (normalmente 993), Username y Password.
4. Pulsa Verificar y confirma que quede activo. Si usarás envío, configura SMTP y verifica su conexión.
5. En Permisos, concede lectura y, si corresponde, envío al cliente.
6. En ChatGPT agrega `https://correo.example.com/mcp`, inicia sesión como cliente y autoriza.
7. Comprueba la lectura y que otro cliente sin permisos no pueda acceder.
8. Para probar un envío, revisa destinatario, asunto y mensaje antes de confirmarlo.

Al cambiar de Ngrok al dominio definitivo, vuelve a conectar ChatGPT: los
tokens MCP están vinculados al origen anterior. El backend ofrece ambos
alcances; el cliente puede elegir únicamente lectura. No se amplía un token
antiguo de manera automática.

## 10. Copias de seguridad y traslado de la base actual

Para una copia local del servidor:

```bash
sudo install -d -o postgres -g postgres -m 0700 /var/backups/corporate-mail-ai
sudo -u postgres /usr/pgsql-18/bin/pg_dump -Fc --no-owner --no-acl \
  -d CorreoCorpAut -f /var/backups/corporate-mail-ai/base-$(date +%Y%m%d-%H%M%S).dump
sudo install -d -o root -g root -m 0700 /var/backups/corporate-mail-ai-secrets
sudo cp --preserve=mode,ownership /etc/corporate-mail-ai/backend.env /var/backups/corporate-mail-ai-secrets/backend.env
```

Programa copias periódicas según la pérdida de datos que puedas aceptar y
guarda también una copia protegida fuera de la VPS. La base sola no permite
recuperar las contraseñas cifradas: necesitas su `MAILBOX_ENCRYPTION_KEY` y versión.
No guardes claves ni dumps en Git, `/var/www`, correos o capturas de pantalla.

Para trasladar los datos de Windows usa `pg_dump` de PostgreSQL 18 con formato
custom y `--no-owner --no-acl`; utiliza contraseña interactiva, no en argumentos.
En la VPS nueva, **restaura antes del paso 6**, sobre la base vacía ya creada:

```bash
/usr/pgsql-18/bin/pg_restore -h 127.0.0.1 -U corporate_mail_owner \
  -d CorreoCorpAut --no-owner --no-acl --exit-on-error -W /ruta/protegida/base.dump
```

No combines una restauración con tablas creadas previamente por Alembic o
seeder. Después ejecuta migraciones pendientes y los GRANT del paso 6.
Una restauración de producción debe ensayarse en una base separada.

## 11. Actualizaciones y recuperación

Antes de actualizar, guarda dump, entorno y commit actual (`git rev-parse HEAD`).
Usa una ventana de mantenimiento. Como usuario de despliegue:

```bash
cd /opt/corporate-mail-ai
sudo systemctl stop corporate-mail-ai
git pull --ff-only
backend/.venv/bin/python -m pip install ./backend
backend/.venv/bin/python -m pip check
cd frontend
npm ci
VITE_API_BASE_URL=/api npm run build
cd ..
sudo chgrp -hR corporate-mail-ai /opt/corporate-mail-ai
sudo chmod -R g-w,o-rwx /opt/corporate-mail-ai
sudo systemctl start corporate-mail-ai-migrate
# Revisa y aplica los GRANT del paso 6 si cambiaron las tablas.
sudo rsync -a --delete frontend/dist/ /var/www/corporate-mail-ai/
sudo chown -R root:root /var/www/corporate-mail-ai
sudo systemctl start corporate-mail-ai
curl --fail https://correo.example.com/api/health/ready
```

Detén el procedimiento ante cualquier fallo y conserva la API detenida hasta
resolverlo o recuperar la versión anterior. Conserva una copia del `dist`
y del entorno Python anterior.
No ejecutes `alembic downgrade` automáticamente para recuperar una versión:
algunas revisiones retiran datos. Recupera código, dependencias, base y claves
compatibles a partir de una copia probada.

## 12. Diagnóstico

```bash
sudo systemctl status corporate-mail-ai caddy postgresql-18 --no-pager
sudo journalctl -u corporate-mail-ai -n 80 --no-pager
sudo journalctl -u corporate-mail-ai-migrate -n 50 --no-pager
sudo journalctl -u caddy -n 80 --no-pager
sudo ss -ltnp
sudo ausearch -m AVC -ts recent
```

| Síntoma | Comprobar |
|---|---|
| 502 | API en 127.0.0.1:8000, servicio y permisos SELinux del proxy |
| Disponibilidad 503 | PostgreSQL, rol/contraseña, GRANT y revisión Alembic actual |
| Frontend 403 | Permisos de `/var/www/corporate-mail-ai` y etiquetas SELinux |
| Certificado pendiente | A/AAAA, puertos 80/443 y logs de Caddy |
| Sin buzones en consentimiento | Cuenta del cliente, permisos y buzón activo/verificado |
| No permite seleccionar envío | SMTP + concesión de envío + solicitud OAuth con mail:send |
| Error IMAP | Host, puerto IMAP del proveedor y Password; no usar POP3 995 como IMAP |
| Lectura funciona pero envío no | SMTP 465/TLS o 587/STARTTLS, autenticación y salida permitida por la VPS |
| Clave de buzón no descifrable | Clave y versión originales de la base restaurada |

No publiques logs que contengan URLs OAuth, tokens o credenciales. Las unidades
incluidas desactivan el registro de accesos de Uvicorn; Caddy no activa logs
de acceso con las plantillas de este repositorio.
