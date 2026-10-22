# Migraciones

20261021_0001 crea las siete tablas principales sin triggers.
20261021_0002 agrega el indicador de administrador unico y tres tablas OAuth.
20261021_0003 agrega usuario unico y permite correo opcional cuando existe
un nombre de usuario. No crea tablas adicionales.
20261021_0004 cambia trece claves foraneas a ON DELETE CASCADE para eliminar
los datos de una empresa desactivada. No elimina datos al aplicar la revision.
El caso de uso comprueba el estado bajo bloqueo y registra la eliminacion
como evento global. Los usuarios y los clientes OAuth globales se conservan.

Desde backend/, para revisar solo el cambio pendiente:

~~~powershell
.\.venv\Scripts\python.exe -m alembic upgrade 20261021_0001:head --sql
~~~

Para aplicarlo cuando corresponda:

~~~powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
~~~

La migracion conserva las tablas y los datos existentes; no promociona usuarios
a administrador automaticamente. Despues crear o promover el administrador
con python -m app.cli como explica el README principal.

Las migraciones usan MIGRATION_DATABASE_URL si existe o DATABASE_URL.
La cuenta de ejecucion puede ser distinta de la propietaria del esquema.
El arranque no ejecuta migraciones ni create_all().

El registro ORM contiene diez tablas y fija search_path=public.
La autogeneracion compara solo esas tablas; no elimina tablas ajenas.
Revisar cualquier revision autogenerada antes de aplicarla.

seeder/01_schema.sql es la alternativa completa de instalacion manual en
una base vacia. Incluye la tabla y revision tecnica de Alembic, por lo que
las actualizaciones futuras se aplican con upgrade head. No ejecutar el
SQL y las migraciones iniciales para crear las mismas tablas. El script
de validacion comprueba que ambas alternativas producen el mismo esquema.
El downgrade de 0002 elimina las autorizaciones OAuth y el indicador del
administrador; usarlo solo con un respaldo y una decision explicita.
