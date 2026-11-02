# Política de seguridad de la información para sistemas internos

Documento: POL-SEG-002 · Versión 4.0 · Dueño: Oficial de Seguridad de la Información (CISO)

## 1. Clasificación de la información

- **Pública**: puede divulgarse sin restricción.
- **Interna**: es para uso de los empleados, como procedimientos y manuales técnicos.
- **Confidencial**: datos personales de empleados o clientes, información financiera y contratos.
- **Restringida**: credenciales, llaves de cifrado, secretos de aplicaciones y planes estratégicos.

Las solicitudes en GESOL no deben contener información **Restringida**. Si un usuario adjunta una contraseña o una llave, la mesa de servicio debe eliminar el adjunto y pedir la rotación inmediata de esa credencial.

## 2. Gestión de accesos

- Los accesos se otorgan con el principio de mínimo privilegio y con la aprobación del jefe directo.
- La revisión de accesos a sistemas críticos es **trimestral**. Los accesos que no se ratifiquen se revocan automáticamente.
- Las cuentas inactivas por más de 60 días se deshabilitan.
- Las cuentas de servicio no pueden usarse para iniciar sesión de forma interactiva.

## 3. Secretos y credenciales

- Los secretos de aplicaciones se almacenan en el gestor de secretos corporativo. Nunca van en el código fuente, en archivos de configuración versionados ni en tickets.
- Las contraseñas de cuentas de servicio se rotan cada 90 días.
- Las contraseñas de usuario deben tener al menos 12 caracteres y se cambian cada 180 días.

## 4. Retención y privacidad

- Las solicitudes y sus adjuntos se conservan durante **5 años** desde su cierre. Después se eliminan o se anonimizan.
- Los logs de auditoría de sistemas críticos se conservan durante 1 año.
- El tratamiento de datos personales sigue la Ley 1581 de 2012 de protección de datos personales de Colombia.

## 5. Uso de inteligencia artificial

- Las herramientas de IA aprobadas solo pueden procesar información Pública e Interna, salvo autorización expresa del CISO.
- Los asistentes de IA deben registrar cada interacción para auditoría y deben citar las fuentes de sus respuestas.
- Está prohibido enviar información Confidencial o Restringida a servicios de IA públicos no contratados por la compañía.

## 6. Reporte de incidentes de seguridad

Cualquier sospecha de incidente de seguridad (phishing, fuga de datos, acceso no autorizado) debe reportarse en las 2 horas siguientes a la mesa de servicio. La mesa lo registra como P1 y lo escala al equipo de Seguridad.
