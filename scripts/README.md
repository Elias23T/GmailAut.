# Scripts locales

configure_secrets.py prepara backend/.env y genera secretos faltantes sin
sobrescribir claves validas ni imprimirlas.

validate_schema.py crea un PostgreSQL temporal autenticado y limitado a
loopback, comprueba restricciones y permisos, detiene el servidor y elimina
su directorio temporal verificado. No usa las credenciales de la base real.

Instala seeder/01_schema.sql en una base vacia del cluster temporal.
Con --backend-python crea otra base con las migraciones completas, compara
columnas, restricciones e indices y ejecuta la suite REST/OAuth/MCP contra
la instalacion SQL, usando correo simulado. Agregar --include-oauth comprueba
tambien las restricciones OAuth. El rol limitado de pruebas se crea solo
dentro de ese cluster temporal; no se usa ningun SQL auxiliar de instalacion.

El administrador se prepara desde backend/ con python -m app.cli
create-admin --email ...; el comando solicita una contraseña sin mostrarla.
promote-admin --email ... permite adoptar una cuenta existente.
