# Guía técnica del sistema legado GESOL

Documento: GT-GESOL-01 · Versión 2.4 · Equipo: Aplicaciones Corporativas

## 1. Descripción general

GESOL es la aplicación de gestión de solicitudes internas de la compañía. Entró en producción en 2014 y la usan cerca de 1.800 empleados. Permite registrar solicitudes, asignarlas a grupos resolutores, controlar los SLA y generar reportes de gestión.

## 2. Arquitectura actual

- **Tipo**: aplicación web monolítica.
- **Lenguaje y frameworks**: Java 8 con Struts 1.3 y Hibernate 3.
- **Servidor de aplicaciones**: Oracle WebLogic 12c, en un clúster de 2 nodos (gesol-app01 y gesol-app02) detrás de un balanceador F5.
- **Base de datos**: Oracle Database 12c en un servidor dedicado (gesol-db01). El esquema principal es GESOL_OWN y tiene aproximadamente 420 GB.
- **Autenticación**: LDAP corporativo (Active Directory), sin inicio de sesión único (SSO).
- **Integraciones**: servicios SOAP con SAP ECC para centros de costo y un archivo plano diario hacia el sistema de nómina.
- **Infraestructura**: máquinas virtuales VMware en el centro de datos principal de Bogotá. El ambiente de contingencia está en Medellín y se sincroniza con Oracle Data Guard.

## 3. Procesos batch

| Proceso | Horario | Descripción |
|---|---|---|
| JOB_SLA_CALC | Cada 15 minutos | Recalcula el consumo de SLA de las solicitudes abiertas |
| JOB_CIERRE_AUTO | 01:00 diario | Cierra las solicitudes resueltas con más de 3 días hábiles sin respuesta |
| JOB_EXPORT_NOMINA | 02:30 diario | Genera el archivo plano para nómina |
| JOB_REPORTES | 05:00 diario | Construye las tablas de reportes de gestión |

Si JOB_EXPORT_NOMINA falla, debe reejecutarse antes de las 07:00, porque nómina carga el archivo a las 07:30.

## 4. Limitaciones conocidas

- Java 8 y Struts 1.3 están fuera de soporte. Struts 1.x tiene vulnerabilidades conocidas sin parche oficial.
- No expone API REST: las integraciones nuevas requieren desarrollo en SOAP o acceso directo a la base de datos.
- Escalamiento solo vertical. En los cierres de mes, el tiempo de respuesta supera los 6 segundos.
- Los despliegues son manuales, con una ventana de mantenimiento los domingos de 22:00 a 02:00.
- La búsqueda de texto en solicitudes históricas usa LIKE sobre columnas CLOB y es muy lenta.

## 5. Operación básica

- **Logs de aplicación**: /u01/logs/gesol/app.log en cada nodo, con rotación diaria y retención de 30 días.
- **Reinicio controlado**: se hace por nodo desde la consola de WebLogic. Primero se saca el nodo del balanceador, se espera a que no tenga sesiones activas y luego se reinicia. Nunca se reinician los dos nodos al mismo tiempo en horario hábil.
- **Monitoreo**: Nagios revisa la URL /gesol/health cada minuto y alerta al grupo de Guardia de Infraestructura.

## 6. Recomendación de modernización aprobada

El Comité de Arquitectura aprobó en 2025 una estrategia de modernización por fases (patrón *strangler fig*):

1. **Fase 1, replataforma**: mover la aplicación a contenedores en la nube sin cambiar el código, y migrar la base de datos a PostgreSQL administrado.
2. **Fase 2, exponer APIs**: crear una capa de API REST delante de GESOL para las integraciones nuevas.
3. **Fase 3, refactorización**: reemplazar por módulos los componentes de Struts por microservicios, empezando por el módulo de reportes y luego el de SLA.
4. **Fase 4, capacidades de IA**: incorporar un asistente inteligente para consultar documentación y el historial de solicitudes.

La estimación preliminar de la Fase 1 es de 4 meses con un equipo de 5 personas.
