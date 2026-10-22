# Backend Corporate Mail AI

Monolito modular con entidades y contratos en domain, casos de uso en application,
adaptadores en infrastructure y controladores en presentation. REST y MCP
comparten autorizacion, lectura IMAP, cifrado y auditoria.

## Acceso

Solo existe un administrador de plataforma, identificado por
users.is_platform_admin y protegido por un indice unico parcial. Crear ese
administrador mediante python -m app.cli create-admin --email ... o
python -m app.cli create-admin --username admin despues de aplicar Alembic.
El comando solicita la contraseña de forma interactiva y exige al menos 12
caracteres; no se crea una contraseña predeterminada en las migraciones.
promote-admin permite adoptar una cuenta existente mediante correo o usuario.
El registro HTTP publico y las rutas para modificar roles no estan habilitados.
Las columnas de rol preexistentes se conservan por compatibilidad de datos;
no conceden administracion de plataforma.

El administrador crea empresas y clientes, puede vincular un cliente existente
a otra empresa, configura buzones y concede permisos explicitos. Los clientes
solo consumen sus buzones y autorizan la vinculacion con ChatGPT.

## Configuracion

backend/.env conserva la conexion y los secretos; nunca debe publicarse.
Las variables de entorno tienen prioridad. Configurar:

| Variable | Uso |
| --- | --- |
| DATABASE_URL | Conexion PostgreSQL del proceso |
| MIGRATION_DATABASE_URL | Conexion DDL opcional para Alembic |
| JWT_SECRET | Secreto aleatorio de al menos 32 caracteres |
| JWT_MINUTES | Sesion del panel, 30 minutos por defecto |
| MAILBOX_ENCRYPTION_KEY | 32 bytes aleatorios en Base64 URL-safe |
| MAILBOX_ENCRYPTION_KEY_VERSION | Version de la clave activa |
| PUBLIC_BASE_URL | Origen externo del backend, sin ruta ni barra final |
| FRONTEND_URL | Origen de la pantalla de acceso y consentimiento |
| OAUTH_REDIRECT_URIS | Lista JSON de callbacks exactos autorizados |
| CORS_ORIGINS | Lista JSON de origenes web permitidos |
| IMAP_TIMEOUT | Espera de red, 10 segundos por defecto |
| IMAP_MAX_MESSAGE_BYTES | Mensaje maximo, 1 MiB por defecto |
| IMAP_ALLOW_PRIVATE_HOSTS | false; habilitar solo para una red interna controlada |

En desarrollo: PUBLIC_BASE_URL=http://127.0.0.1:8000 y
FRONTEND_URL=http://127.0.0.1:5173. En produccion ambos usan el mismo
origen, por ejemplo https://correo.tudominio.com. HTTP solo se acepta en
localhost. La plantilla Caddy enruta /api/*, /mcp, /oauth/* y /.well-known/*.

El callback inicial permitido es
https://chatgpt.com/connector_platform_oauth_redirect.
Usar siempre la URL exacta indicada en la configuracion del servidor en
ChatGPT. El registro dinamico rechaza otros callbacks y clientes con secretos.
No hay CIMD ni OIDC en esta version; seleccionar DCR y cliente publico con PKCE.

El script scripts/configure_secrets.py genera secretos faltantes sin imprimirlos.
Conservar la clave de cifrado: esta version admite una sola clave activa;
cambiarla requiere recifrar las credenciales guardadas.

## Rutas

Ver /docs para cuerpos y contratos. Salvo login, health, descubrimiento,
registro OAuth y autorizacion inicial, las rutas requieren autenticacion.

| Ruta | Funcion |
| --- | --- |
| POST /auth/login; GET /auth/me | Sesion propia, distinta de los tokens MCP |
| GET, POST /tenants | Empresas del administrador |
| PATCH /tenants/{id} | Renombrar empresa |
| GET, POST /admin/clients | Listar o crear clientes por empresa |
| POST /admin/clients/link | Vincular cliente existente por email |
| PATCH /admin/clients/{id}?tenant_id=... | Activar o suspender una cuenta |
| GET, POST /tenants/{id}/mailboxes | Configuracion de buzones |
| PATCH /tenants/{id}/mailboxes/{box} | Configuracion, estado y credenciales |
| GET, POST /tenants/{id}/mailboxes/{box}/grants | Permisos de lectura |
| DELETE /tenants/{id}/mailboxes/{box}/grants/{member} | Revocar lectura |
| POST /tenants/{id}/mailboxes/{box}/check | Validar IMAP como administrador |
| GET /tenants/{id}/mailboxes/{box}/messages | Buscar INBOX |
| GET /tenants/{id}/mailboxes/{box}/messages/{uid}?uid_validity=... | Leer correo |
| GET /tenants/{id}/audit | Auditoria del administrador |
| GET /admin/connection-settings | URL MCP y estado de configuracion |
| GET /admin/connections?tenant_id=... | Vinculaciones OAuth |
| DELETE /admin/connections/{member}?tenant_id=... | Revocar todas las conexiones del cliente en la empresa |
| GET /.well-known/oauth-authorization-server | Descubrimiento OAuth |
| GET /.well-known/oauth-protected-resource/mcp | Descubrimiento del recurso |
| POST /oauth/register | Registro dinamico con callback permitido |
| GET /oauth/authorize | Validar solicitud y abrir la pantalla de consentimiento |
| POST /oauth/context; POST /oauth/consent | Revisar permisos y aprobar o rechazar |
| POST /oauth/token; POST /oauth/revoke | Intercambio, renovacion y revocacion |
| POST /mcp | Protocolo MCP mediante SDK oficial |

Los formularios OAuth usan application/x-www-form-urlencoded.
El resto de formularios REST usa JSON. Los listados de correo y auditoria
tienen paginacion y limites de servidor.

GET /health verifica el proceso. GET /health/ready comprueba PostgreSQL
y la revision de esquema requerida. Ningun arranque ejecuta migraciones.

## Vinculacion OAuth

Flujo authorization_code con PKCE S256 obligatorio, scope mail:read,
resource exacto y callback registrado. La solicitud de consentimiento esta
firmada y expira en cinco minutos; el codigo expira en 90 segundos y solo
puede consumirse una vez. El callback conserva state e incluye iss.

Tokens opacos aleatorios: solo se guardan sus hashes SHA-256. El acceso dura
15 minutos y la renovacion tiene un horizonte fijo de siete dias desde la
autorizacion. Se rota el refresh token en cada uso. La reutilizacion de un
codigo o refresh token consumido revoca su familia de tokens.
La emision y revocacion se serializan por membresia en PostgreSQL.

Cada peticion MCP comprueba token, audiencia, scopes, cliente OAuth, usuario,
empresa y membresia activos. Cada lectura comprueba el permiso explicito.
Se revalida la autorizacion despues de IMAP antes de devolver contenido.
Suspender un cliente revoca todas sus vinculaciones; reactivarlo requiere
autorizar ChatGPT de nuevo. Revocar tambien invalida codigos aun no canjeados.

El transporte es Streamable HTTP sin estado, con respuestas JSON y limites
de cuerpo de 64 KiB. El SDK controla protocolo, autenticacion y validacion
de Host/Origin. Login y endpoints OAuth sensibles limitan intentos por IP y
proceso; el despliegue distribuido requerira un limitador compartido.

No se llama a la API de OpenAI desde el backend ni se necesita una API key
para servir estas herramientas. ChatGPT realiza el resumen con el correo
obtenido mediante las herramientas de lectura.

## Correo y datos

Credenciales IMAP cifradas con AES-256-GCM y UUID del buzon como AAD.
TLS verifica certificados y fija la direccion DNS para la conexion. Se
rechazan destinos privados por defecto e inyecciones de comandos.
Maximo cuatro conexiones IMAP simultaneas por proceso.

INBOX se abre con EXAMINE y se consulta con BODY.PEEK. Busqueda por asunto
o remitente y filtro de no leidos. Cada lectura verifica UID y UIDVALIDITY.
El HTML se convierte en texto sin ejecutar scripts ni cargar recursos remotos.
Adjuntos: nombres solamente. El cuerpo puede indicar truncated=true.
No se persisten correos ni resumenes.

Auditoria por accion, actor, empresa, buzon, peticion y origen REST/MCP, sin
contenido, busquedas o secretos. Si se usa una cuenta PostgreSQL limitada,
el administrador de la base concede SELECT, INSERT, UPDATE y DELETE en las
nueve tablas de aplicacion restantes, solo SELECT e INSERT en audit_events,
y SELECT en alembic_version para la comprobacion de disponibilidad.
Los roles se administran por separado: seeder/01_schema.sql reproduce las
tablas reales sin crear cuentas PostgreSQL ni asignar contrasenas. Las
migraciones tampoco crean ni elevan usuarios PostgreSQL.

## Validacion

Desde la raiz, ejecutar scripts/validate_schema.py con --backend-python
y --include-oauth como indica el README principal. Las pruebas cubren
migraciones, esquema ORM, cifrado, lectura IMAP, permisos, aislamiento,
consentimiento, PKCE, rotacion, expiracion, revocacion y llamadas MCP reales
con proveedor de correo simulado.

No se incluyen recuperacion de contraseña, verificacion de email, OIDC ni
rotacion automatica de claves. El acceso inicial es gestionado por el
administrador y se entrega por un canal privado.

Referencias oficiales de OpenAI:
[autenticacion](https://developers.openai.com/plugins/build/auth) y
[conexion y pruebas](https://developers.openai.com/plugins/deploy/connect-chatgpt).
