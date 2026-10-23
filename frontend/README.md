# Frontend Corporate Mail AI

En producción Caddy sirve `dist` y reenvía `/api` al backend en el mismo
subdominio. La compilación exige `VITE_API_BASE_URL=/api` y no utiliza
`VITE_PUBLIC_URL`; este último ajuste corresponde únicamente al servidor
de desarrollo. No se instala ni se ejecuta Ngrok en la VPS.

Vue 3, Vite y TypeScript. Iniciar con npm install y npm run dev.
La API local debe responder en http://127.0.0.1:8000.
src/api.ts usa /api; Vite y Caddy retiran ese prefijo para REST.
Para pruebas con ngrok, Vite tambien reenvia /mcp, /oauth y /.well-known al
backend. VITE_PUBLIC_URL en .env.local permite solo el hostname concreto
del tunel; el puerto del frontend permanece en 5173. Ver README principal.

El panel usa un tema claro con acentos turquesa en src/admin-theme.css.
AppIcon.vue centraliza los iconos SVG sin dependencias externas. El encabezado
incluye guia y perfil, y el menu se contrae en escritorio y se abre sobre
el contenido en movil. Clientes y Buzones incluyen busqueda y filtros de
estado sobre los registros obtenidos de la API; las metricas usan esos datos.

## Pantallas

- Inicio de sesion centrado en una sola tarjeta, con usuario o correo,
  contrasena y control para mostrarla u ocultarla, sin registro publico.
- Panel del unico administrador: empresas, clientes, buzones y permisos.
- Empresas: listado, busqueda, creacion y edicion mediante modal, cambios
  de estado y eliminacion confirmada solo para empresas desactivadas.

- Clientes → Conexion ChatGPT: copiar URL MCP y revocar autorizaciones.
- Lectura de correo de solo texto.
- /connect: acceso y consentimiento del cliente durante la vinculacion OAuth.

Al crear o editar una empresa solo se solicita el nombre. La API genera
un identificador interno unico cuando se omite slug; no se muestra en el
formulario ni en el listado, y se conserva al cambiar el nombre.

El administrador puede crear un cliente nuevo o vincular uno existente a
otra empresa. La contraseña de plataforma permite autorizar ChatGPT;
las credenciales IMAP se configuran por separado y nunca se muestran.
El formulario de buzon reune en un solo modal los indicadores del proveedor:
URL, Username, Password, Incoming Server, IMAP Port, Outgoing Server y SMTP Port.
Todos los campos se muestran sin opciones desplegables adicionales. URL es
opcional y guarda la direccion HTTPS del webmail como referencia, sin usarla
como servidor de correo. Username completa el correo automaticamente si es
una direccion de correo; se permite ajustar el correo si el usuario es distinto.
Nombre visible es opcional y utiliza el correo si queda vacio. Al editar,
Username y Password vacios conservan los valores guardados. POP3 no se usa.
SMTP tiene una casilla de habilitacion y exige TLS directo o STARTTLS. La comprobacion
SMTP autentica sin enviar correos. Permisos permite conceder lectura y envio
por separado al cliente, y habilitar el envio de la propia cuenta administradora.
La pantalla de consentimiento distingue lectura de envio segun los alcances
OAuth solicitados. Las conexiones nuevas anuncian y ofrecen mail:read y
mail:send; el envio permanece desmarcado y requiere tanto permiso del
administrador como eleccion explicita del cliente. Una solicitud que pide
solo mail:read no se amplia desde el consentimiento. Si ChatGPT conserva
una configuracion anterior de solo lectura, elimina esa configuracion del
complemento y vuelve a agregar la URL MCP para conectar con ambos alcances.
Un permiso de lectura no sustituye la verificacion IMAP: solo los buzones
activos aparecen para conectar ChatGPT. Si un buzon autorizado esta pendiente
o deshabilitado, el consentimiento explica su estado y permite actualizar
los buzones despues de que el administrador lo verifique. El modal de Permisos
tambien avisa si falta ese paso. Se recuerda usar IMAP Port (habitualmente
993), no el puerto POP3 995.
Los formularios muestran etiquetas y campos sin parrafos de ayuda extensos.
Se conservan errores, validaciones, confirmaciones y avisos operativos.
Clientes mantiene minimo 6 caracteres para la contraseña de plataforma;
Buzones acepta la contraseña del proveedor. Al editar, los placeholders
indican que una contraseña vacia conserva la actual. Gmail mantiene un
placeholder para su clave de aplicacion. Todos los campos de contraseña
conservan el boton para mostrar u ocultar su valor.
Vincular muestra las cuentas existentes que aun no pertenecen a la empresa
seleccionada, incluidas las conservadas al eliminar otra empresa. La lista
solo puede consultarla el administrador con acceso a la empresa. Vincular
conserva la contraseña y el estado de la cuenta y no concede permisos de
buzones automaticamente. El listado principal muestra todas las cuentas,
incluidas las que quedaron sin empresa, con buscador y filtro de estado.
Cada fila muestra sus empresas y permite configurar acceso, activar,
suspender, retirar una cuenta suspendida o vincularla a la empresa elegida.
El selector de empresa se utiliza para altas y vinculaciones; no oculta
cuentas del listado. Las metricas cuentan todas las cuentas de cliente.
La retirada libera usuario y correo y conserva la auditoria. El aviso de
usuario duplicado busca la cuenta directamente en esta misma tabla.
Eliminar clientes suspendidos solicita confirmacion con el total de cuentas
de todas las empresas y sin empresa, independientemente del buscador o filtro.
Solo se envian los identificadores revisados al abrir la confirmacion. Si una
cuenta fue activada o eliminada entretanto, no se elimina ninguna y se pide
actualizar el listado. Las cuentas habilitadas y la auditoria se conservan.

El menu contiene Buzones, Empresas, Clientes y Administradores. La empresa se elige desde
el listado con Usar empresa o desde el selector del contenido de Buzones y
Clientes. Las empresas desactivadas permanecen visibles en Empresas.
Actividad no se muestra en el menu; la API mantiene el registro de auditoria.

Clientes contiene las vistas Clientes autorizados y Conexion ChatGPT dentro
del mismo componente. Al volver a Clientes autorizados se conservan la
busqueda y los filtros. La vista de conexiones consulta de nuevo la API al
abrirse para reflejar las autorizaciones vigentes.

Clientes permanece visible aunque no haya una empresa activa: muestra las
pestanas, contadores y herramientas. El selector de empresa esta dentro de
Clientes. Sin empresa, Agregar y Vincular explican el requisito en un modal;
no se envian peticiones de clientes o autorizaciones sin tenant_id. La URL
MCP de la plataforma puede consultarse desde Conexion ChatGPT igualmente.
Al cambiar de empresa se limpia el listado y se descartan respuestas de
consultas anteriores para evitar mostrar clientes de otro espacio.

Los formularios de empresa, cliente y buzon, los permisos y las vistas de
correo usan el mismo componente AppModal.vue. ConfirmModal.vue reutiliza
esa base para confirmar cambios de acceso y cierre de sesion. Para nuevas
acciones, usar estos componentes con open, title, busy, evento close y los
slots de contenido y footer. El modal administra foco, Escape, fondo y
desplazamiento; busy impide cerrarlo mientras se guarda. Los errores se
muestran dentro del modal y las contraseñas se limpian al cerrar.

Los clientes autenticados fuera de una solicitud OAuth ven instrucciones
para iniciar la conexion desde ChatGPT. La API comprueba los permisos;
las restricciones no dependen de que un boton este oculto.

El JWT se mantiene en memoria y se pierde al recargar. No se guardan tokens
ni passwords en localStorage. La solicitud OAuth se conserva en memoria
y se retira de la barra de direcciones tras abrir la pantalla.

El correo se muestra como texto con interpolacion de Vue. No se usa v-html
ni se cargan recursos remotos del correo. La pantalla de consentimiento
indica que el contenido consultado se compartira con ChatGPT.

npm run build valida TypeScript y genera dist/. La pantalla muestra
Desarrollo local hasta configurar PUBLIC_BASE_URL con un dominio HTTPS.
