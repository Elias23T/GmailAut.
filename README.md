# Corporate Mail AI

Plataforma de lectura y envio autorizado de correo corporativo desde ChatGPT mediante MCP.
FastAPI, Vue 3, TypeScript y PostgreSQL. Despliegue nativo con Uvicorn,
Caddy y systemd, sin Docker.

Instalación en VPS: [guía de producción para AlmaLinux](docs/PRODUCCION_ALMALINUX.md).

## Entrega para Git y VPS

El despliegue usa un subdominio propio con HTTPS. Ngrok es opcional para
pruebas locales y no forma parte del funcionamiento en producción.

El responsable de despliegue debe clonar el repositorio y seguir la guía de
AlmaLinux. Necesitará el subdominio, acceso a la VPS y decidir si crea una base
vacía o traslada `CorreoCorpAut`. Si traslada los datos, la clave original de
cifrado se entrega por separado y no mediante Git.

La entrega incluye backend, frontend, migraciones, seeder, pruebas, scripts y
plantillas de Caddy/systemd. Git excluye `.env`, archivos `*.env`, claves,
dumps, cachés, `.venv`, `node_modules` y `dist`. Las dependencias se instalan
y el frontend se compila en el servidor con `npm ci` y `npm run build`.
Las plantillas `.env.example` sí forman parte del repositorio.
La compilación requiere `VITE_API_BASE_URL=/api`; no incorpora la dirección
del túnel local. Configura `PUBLIC_BASE_URL` y `FRONTEND_URL` con el mismo
origen HTTPS. La URL MCP final será `https://SUBDOMINIO/mcp`.

## Funcionamiento

Los administradores gestionan empresas, clientes y buzones. El registro publico
esta cerrado. Los clientes inician sesion para autorizar ChatGPT mediante
OAuth; solo pueden consultar los buzones que se les hayan asignado.

El menu incluye Buzones, Empresas, Clientes y Administradores. Conexion ChatGPT esta dentro
de Clientes. La actividad se registra internamente para auditoria. Un cliente
puede pertenecer a varias empresas. Cada vinculacion OAuth selecciona una
empresa y se limita a sus permisos, que se comprueban en cada consulta.

MCP expone list_mailboxes, search_mail, read_mail, prepare_email y send_email mediante el SDK oficial.
REST y MCP reutilizan los mismos casos de uso. ChatGPT puede elaborar
resumenes con el contenido consultado; el backend no ejecuta un modelo de IA.
La lectura no modifica mensajes. El envio requiere SMTP habilitado, permiso
por buzon y OAuth mail:send, con preparacion y confirmacion del contenido.
No se eliminan ni marcan mensajes.

## Preparar la instalacion local

La conexion existente de backend/.env se conserva. La revision actual es
20261023_0008; las migraciones se aplican de forma explicita antes del arranque.

Desde backend/, en PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli create-admin --email tu-correo@empresa.com --name "Administrador"
~~~

El comando solicita la contraseña por consola, sin mostrarla ni guardarla
en argumentos. Usa al menos 6 caracteres. Si ya tenias una cuenta propia
y quieres convertirla en administrador, usa promote-admin con su
email en lugar de create-admin. No se crean cuentas ni passwords por defecto.

Iniciar el backend desde backend/:

~~~powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
~~~

En otra terminal, desde frontend/:

~~~powershell
npm install
npm run dev
~~~

Interfaz: http://127.0.0.1:5173. API: http://127.0.0.1:8000/docs.
En Empresas, crear una empresa y seleccionarla con Usar empresa.
Solo se escribe su nombre; el identificador interno se genera automaticamente.
Agregar el cliente, configurar y verificar sus buzones,
y concederle lectura desde Buzones → Permisos.

Empresas permite listar, buscar, editar, activar y desactivar. Solo se puede
eliminar una empresa desactivada, con confirmacion. Se eliminan en cascada sus
buzones, credenciales, permisos, membresias, autorizaciones OAuth y actividad.
Las cuentas globales de usuarios y los correos del proveedor se conservan.
La desactivacion revoca los tokens existentes; activar no los restablece.
La revision 20261021_0004 configura las claves foraneas para esta cascada;
aplicarla no elimina empresas ni datos.

## Base de datos

Se conservan las siete tablas principales. La nueva migracion agrega
is_platform_admin a users y las tres tablas que antes estaban reservadas
para OAuth: oauth_clients, oauth_authorization_codes y oauth_tokens.
La revision 20261022_0005 agrega SMTP opcional, can_send y outgoing_messages
para controlar preparaciones y evitar reenvios. Son once tablas de aplicacion,
mas alembic_version (doce en total). No hay triggers de aplicacion ni copias
permanentes del contenido del correo en PostgreSQL. Las preparaciones se
guardan cifradas durante el flujo de confirmacion.

## Envio y respuestas

En Buzones → Editar, habilitar envio y configurar servidor SMTP, puerto y
seguridad (TLS directo, normalmente 465; STARTTLS obligatorio, normalmente
587). Se reutiliza el usuario y la contraseña cifrada del buzon. Verificar
SMTP solo autentica; no envia un mensaje. En Permisos conceder envio al
cliente. La cuenta administradora gestiona la plataforma; no se utiliza para
autorizar ChatGPT.

En Clientes, asignar un usuario y una contraseña de Corporate Mail AI a cada
cliente. Para las cuentas existentes, usar Configurar acceso. La contraseña
del buzon sigue siendo independiente. El cliente conecta la URL MCP en su
propio ChatGPT, inicia sesion con sus credenciales y elige solo lectura o,
si ChatGPT lo solicita y el administrador lo habilito, tambien envio.
El envio viene desmarcado y nunca concede permisos superiores a los del buzon.
Cambiar el usuario o la contraseña invalida sus sesiones y conexiones OAuth
en todas las empresas; la contraseña actual nunca se devuelve.

Una conexion anterior de ChatGPT conserva su alcance de lectura. Actualizar
las herramientas del complemento y autorizar nuevamente mail:read mail:send.
prepare_email devuelve remitente, destinatario, asunto y cuerpo para revisar;
send_email requiere el mismo contenido y confirmed=true. Los borradores
expiran en diez minutos y pertenecen a la cuenta y empresa que los preparo.
Una misma preparacion no vuelve a enviarse despues de ser reservada o aceptada.
Un resultado SMTP incierto se informa sin reintentos automaticos.

Las respuestas usan Reply-To/From y Message-ID/References del mensaje original
para conservar el hilo. Esta version admite texto y un destinatario, sin
adjuntos, CC ni CCO. SMTP confirma aceptacion por el servidor, no entrega final.
No se agrega automaticamente una copia a Enviados; depende del proveedor.

La revision 20261021_0003 permite ingresar con usuario o correo. Las cuentas
con usuario pueden no tener correo asociado; no se inventan direcciones.

seeder/01_schema.sql es el unico SQL de instalacion manual: reproduce el
esquema real completo, con indices, restricciones, cascadas y revision Alembic.
Se ejecuta solo en una base vacia y no incluye cuentas ni credenciales.
Para crear una base nueva se elige ese SQL o alembic upgrade head.
No ejecutar ambos para crear las mismas tablas. Las siguientes actualizaciones
se aplican con Alembic. Los roles PostgreSQL se administran por separado.

## Conectar ChatGPT

En producción se utiliza el subdominio HTTPS de la VPS y su ruta `/mcp`.
Durante el desarrollo se puede probar MCP localmente en http://127.0.0.1:8000/mcp.

Solo para probar desde esta computadora con ngrok, mantener el backend en 127.0.0.1:8000 y el frontend
en 127.0.0.1:5173. Desde otra terminal ejecutar:

~~~powershell
ngrok http http://127.0.0.1:5173
~~~

Configurar PUBLIC_BASE_URL y FRONTEND_URL en backend/.env con el origen HTTPS
del tunel, sin /mcp. Agregar ese origen a CORS_ORIGINS. En frontend/.env.local
configurar VITE_PUBLIC_URL con el mismo origen. Reiniciar ambos servidores
al cambiar estas variables. Vite reenvia /api, /mcp, /oauth y /.well-known
al backend; /connect muestra la pantalla de acceso en el frontend.
La URL para ChatGPT sera ese origen seguido de /mcp. Si cambia el dominio
del tunel, actualizar ambas configuraciones. Mantener los tres procesos
encendidos durante la prueba. Esta configuracion Vite es solo de desarrollo.

Para el despliegue con dominio propio:

1. Configurar PUBLIC_BASE_URL y FRONTEND_URL con el mismo origen HTTPS.
2. Configurar DNS y Caddy usando deploy/caddy/Caddyfile.example.
3. Copiar la URL MCP en Clientes → Conexion ChatGPT: https://tu-dominio/mcp.
4. Agregarla como servidor MCP personalizado en ChatGPT y seleccionar OAuth
   con registro dinamico (DCR), cuando la cuenta permita esta funcion.
5. Verificar que OAUTH_REDIRECT_URIS contenga la URL de retorno exacta
   mostrada por ChatGPT.
6. El cliente inicia sesion en nuestra pantalla, revisa sus buzones y
   autoriza la conexion. Luego activa el complemento en su conversacion.

La URL es compartida; cada conexion tiene sus propios tokens y permisos.
Las credenciales IMAP nunca forman parte de la URL ni se entregan a ChatGPT.
La pantalla distingue la configuracion HTTPS del desarrollo local.
La prueba real en ChatGPT requiere una URL HTTPS accesible, mediante tunel
o despliegue, y una cuenta con la opcion de agregar servidores personalizados.

Detalles de OAuth y despliegue: [backend](backend/README.md).
Referencia: [documentacion oficial de OpenAI](https://developers.openai.com/plugins/build/auth).

## Verificacion

Desde la raiz:

~~~powershell
backend/.venv/Scripts/python.exe scripts/validate_schema.py --pg-bin "C:\Program Files\PostgreSQL\18\bin" --include-oauth --backend-python backend/.venv/Scripts/python.exe
~~~

Crea PostgreSQL temporal, instala el SQL principal, verifica que coincida con
las migraciones completas y ejecuta pruebas con correo simulado.
No utiliza CorreoCorpAut ni sus credenciales. La instancia temporal se detiene
y elimina al terminar. Desde frontend/, npm run build valida TypeScript
y compila la interfaz.

Mas detalles: [migraciones](backend/alembic/README.md), [frontend](frontend/README.md),
[SQL principal](seeder/01_schema.sql) y [scripts](scripts/README.md).
