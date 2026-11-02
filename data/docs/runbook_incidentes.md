# Runbook de incidentes frecuentes

Documento: RB-OPS-011 · Versión 1.7 · Dueño: Guardia de Infraestructura

## 1. GESOL no responde (error 502/504 en el portal)

1. Verifica en Nagios si el health check /gesol/health está fallando en uno o en los dos nodos.
2. Si falla un solo nodo, sácalo del balanceador F5 y revisa /u01/logs/gesol/app.log buscando "OutOfMemoryError" o "Stuck thread".
3. Si encuentras OutOfMemoryError, genera un heap dump con el comando jcmd, reinicia el nodo desde la consola de WebLogic y adjunta el dump a la solicitud.
4. Si fallan los dos nodos, revisa primero la base de datos (paso 3 de este runbook) antes de reiniciar.
5. Registra el incidente en GESOL como P1, porque GESOL es un servicio crítico.

## 2. Falla del proceso JOB_EXPORT_NOMINA

1. Revisa la tabla GESOL_OWN.BATCH_LOG filtrando por JOB_NAME = 'JOB_EXPORT_NOMINA'.
2. La causa más común es el tablespace temporal lleno (error ORA-01652). Pide al DBA que lo amplíe.
3. Reejecuta el job desde el planificador Control-M con la opción "Rerun". Debe terminar antes de las 07:00.
4. Si no termina a tiempo, informa al área de Nómina para que retrase la carga y abre una solicitud P2.

## 3. Lentitud en la base de datos

1. Consulta las sesiones bloqueadas en V$SESSION, filtrando por BLOCKING_SESSION no nulo.
2. Revisa en el reporte AWR de la última hora las consultas con mayor tiempo de ejecución.
3. Si la causa es la búsqueda de texto en solicitudes históricas, pide a los usuarios que filtren por rango de fechas mientras se resuelve.
4. Nunca termines sesiones del usuario SAP_INTEG sin coordinar con el equipo SAP.

## 4. Usuario sin acceso a GESOL

1. Verifica que el usuario exista y esté activo en el Directorio Activo.
2. Confirma que pertenezca al grupo GG_GESOL_USUARIOS.
3. Si cambió de área, el rol en GESOL debe actualizarlo un administrador funcional. No se asignan roles por correo.
4. Es un requerimiento de servicio P4, salvo que impida una operación crítica.

## 5. Contactos por rol

- **Mesa de servicio**: canal #mesa-servicio y extensión interna 4000, disponible 24x7.
- **Guardia de Infraestructura**: según el calendario de guardia publicado en la intranet.
- **DBA de turno**: se escala desde la mesa de servicio.
- **Proveedor WebLogic**: solo a través del Gerente de Operaciones de TI.
