# Corporate Mail AI

Plataforma de lectura de correo corporativo desde ChatGPT mediante MCP.
FastAPI, Vue 3, TypeScript y PostgreSQL. Despliegue nativo con Uvicorn,
Caddy y systemd, sin Docker.

## Funcionamiento

Un administrador gestiona empresas, clientes y buzones. El registro publico
esta cerrado. Los clientes inician sesion para autorizar ChatGPT mediante
OAuth; solo pueden consultar los buzones que se les hayan asignado.

El menu incluye Buzones, Empresas y Clientes. Conexion ChatGPT esta dentro
de Clientes. La actividad se registra internamente para auditoria. Un cliente
puede pertenecer a varias empresas. Cada vinculacion OAuth selecciona una
empresa y se limita a sus permisos, que se comprueban en cada consulta.

MCP expone list_mailboxes, search_mail y read_mail mediante el SDK oficial.
REST y MCP reutilizan los mismos casos de uso. ChatGPT puede elaborar
resumenes con el contenido consultado; el backend no ejecuta un modelo de IA.
No se envian, eliminan, marcan ni modifican correos.

## Preparar la instalacion local

La conexion existente de backend/.env se conserva. La revision actual es
20261021_0004; las migraciones se aplican de forma explicita antes del arranque.

Desde backend/, en PowerShell:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.cli create-admin --email tu-correo@empresa.com --name "Administrador"
~~~

El comando solicita la contraseña por consola, sin mostrarla ni guardarla
en argumentos. Usa al menos 12 caracteres. Si ya tenias una cuenta propia
y quieres convertirla en el unico administrador, usa promote-admin con su
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
Son diez tablas de aplicacion, mas la tabla tecnica alembic_version.
No hay triggers ni correos almacenados en PostgreSQL.

La revision 20261021_0003 permite ingresar con usuario o correo. Las cuentas
con usuario pueden no tener correo asociado; no se inventan direcciones.

seeder/01_schema.sql es el unico SQL de instalacion manual: reproduce el
esquema real completo, con indices, restricciones, cascadas y revision Alembic.
Se ejecuta solo en una base vacia y no incluye cuentas ni credenciales.
Para crear una base nueva se elige ese SQL o alembic upgrade head.
No ejecutar ambos para crear las mismas tablas. Las siguientes actualizaciones
se aplican con Alembic. Los roles PostgreSQL se administran por separado.

## Conectar ChatGPT

Actualmente se puede probar MCP localmente en http://127.0.0.1:8000/mcp.
Para conectar por URL desde ChatGPT, preparar un servidor con dominio HTTPS.

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
El despliegue publico y la prueba real en ChatGPT requieren ese dominio y
una cuenta con la opcion de agregar servidores personalizados.

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
