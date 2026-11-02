# Procedimiento de gestión de solicitudes internas

Código: PR-OPS-004 · Versión 3.2 · Dueño: Gerencia de Operaciones de TI

## 1. Objetivo y alcance

Este procedimiento define cómo se registran, clasifican, atienden y cierran las solicitudes internas que llegan a TI a través del sistema GESOL (Gestión de Solicitudes). Aplica a todas las áreas de la compañía y a los proveedores que operan servicios de TI.

Tipos de solicitud admitidos:

- **Incidente**: interrupción o degradación de un servicio que ya funcionaba.
- **Requerimiento de servicio**: accesos, instalaciones, cambios de configuración o reportes.
- **Cambio evolutivo**: nueva funcionalidad, integración o mejora sobre un sistema existente.
- **Consulta**: duda funcional o técnica que no requiere modificar ningún sistema.

## 2. Ciclo de vida y estados

Toda solicitud recorre estos estados en GESOL:

1. **Registrada**: el solicitante crea la solicitud con título, descripción, sistema afectado y evidencia.
2. **En análisis**: la mesa de servicio valida la información, asigna tipo, prioridad y grupo resolutor. Tiempo máximo en este estado: 1 día hábil.
3. **En desarrollo**: el grupo resolutor trabaja en la solución.
4. **En pruebas**: el solicitante o el equipo de QA valida la solución en el ambiente de pruebas.
5. **Resuelta**: la solución está aplicada en producción y se espera la confirmación del solicitante.
6. **Cerrada**: el solicitante confirma o pasan 3 días hábiles sin respuesta desde que se marcó como Resuelta (cierre automático).
7. **Rechazada**: la solicitud no procede (duplicada, fuera de alcance o sin información). Debe incluir el motivo.

Una solicitud **En espera de usuario** pausa el conteo del SLA hasta que el solicitante responda.

## 3. Clasificación de prioridad y SLA

La prioridad se asigna con base en el impacto, la cantidad de usuarios afectados y si existe una alternativa de trabajo (workaround):

| Prioridad | Criterio | Tiempo de respuesta | Tiempo de resolución |
|---|---|---|---|
| P1 Crítica | Servicio crítico caído sin workaround, o impacto alto con 100 o más usuarios afectados | 1 hora | 4 horas |
| P2 Alta | Impacto alto, servicio crítico con workaround, o 20 o más usuarios afectados | 4 horas | 1 día hábil |
| P3 Media | Impacto medio, o 5 o más usuarios afectados | 1 día hábil | 3 días hábiles |
| P4 Baja | Impacto bajo y menos de 5 usuarios afectados | 2 días hábiles | 10 días hábiles |

Son **servicios críticos**: GESOL, facturación electrónica, nómina, el portal de clientes y la integración con SAP.

Los tiempos de P1 se cuentan en horario 24x7. Las demás prioridades se cuentan en horario hábil: lunes a viernes de 8:00 a 18:00, hora de Colombia.

## 4. Escalamiento

- Si una solicitud P1 no tiene respuesta en 30 minutos, la mesa de servicio escala al Líder de Guardia de Infraestructura.
- Si una P1 o P2 supera el 80 % de su tiempo de resolución, se notifica automáticamente al Gerente de Operaciones de TI.
- Toda P1 requiere un informe post-incidente (postmortem) dentro de los 5 días hábiles siguientes a su cierre.
- Las solicitudes rechazadas pueden apelarse una sola vez ante el Coordinador de Mesa de Servicio.

## 5. Reglas de estimación de esfuerzo

Para cambios evolutivos y requerimientos se usa una estimación inicial por reglas simples, que luego el equipo refina:

- Horas base por tipo de trabajo: corrección 8 h, reporte 16 h, nueva funcionalidad 40 h, integración 60 h y migración 120 h.
- Factor por complejidad: baja ×0,75; media ×1,0; alta ×1,6.
- Se suman 8 horas por cada componente o sistema adicional involucrado.
- Si el trabajo requiere migración de datos, se agrega un 30 %.
- Siempre se agrega un 15 % de contingencia y se reporta un rango de ±20 %.
- Un sprint equivale a 2 semanas y a 60 horas productivas por desarrollador.

Las estimaciones mayores a 200 horas requieren aprobación del Comité de Cambios antes de iniciar.

## 6. Cierre y calidad

- Toda solicitud cerrada debe tener la causa raíz (para incidentes) y la solución aplicada.
- La encuesta de satisfacción se envía al cerrar. La meta de satisfacción es 4,2 sobre 5.
- La meta de cumplimiento de SLA es del 95 % mensual para P1 y P2, y del 90 % para P3 y P4.
