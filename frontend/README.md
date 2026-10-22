# Frontend Corporate Mail AI

Vue 3, Vite y TypeScript. Iniciar con npm install y npm run dev.
La API local debe responder en http://127.0.0.1:8000.
src/api.ts usa /api; Vite y Caddy retiran ese prefijo para REST.

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

El menu contiene Buzones, Empresas y Clientes. La empresa se elige desde
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
