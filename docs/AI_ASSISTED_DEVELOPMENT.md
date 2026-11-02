# Desarrollo asistido por IA (AI-CDL)

> **Nota para el candidato:** este documento describe el proceso real con el que se construyó el repositorio. Complétalo con tus propias validaciones (lo que revisaste, cambiaste y probaste en tu cuenta de AWS) antes de entregarlo. Debe reflejar tu trabajo, y en la entrevista te pueden preguntar por cualquier punto.

## 1. Herramienta usada y enfoque

Usé **Claude Code** (Anthropic) como asistente de desarrollo, en modo *pair programming*. La IA propuso diseño y código; yo definí los requisitos, tomé las decisiones de arquitectura, revisé cada archivo, ejecuté las pruebas y desplegué manualmente en AWS.

Principio de trabajo: **la IA acelera la escritura; la validación y las decisiones son humanas**. Nada se considera terminado hasta que pasa una prueba automatizada o una verificación manual.

## 2. Tareas apoyadas con IA

| Tarea | Aporte de la IA | Mi rol |
|---|---|---|
| Investigación de arquitecturas de referencia | Buscó y resumió guías de AWS (Prescriptive Guidance RAG, Serverless RAG, Well-Architected GenAI Lens) | Elegí la arquitectura final y descarté opciones costosas (OpenSearch Serverless) |
| Análisis del free tier y costos | Identificó que el Free plan limita Bedrock y que OpenSearch Serverless no es viable por costo | Pasé la cuenta al plan pagado conservando los créditos y configuré un presupuesto |
| Scaffolding del proyecto | Estructura de carpetas, FastAPI, esquemas Pydantic y manejo de errores | Revisé los contratos de la API y los nombres |
| Pipeline RAG | Chunking por secciones, cliente de S3 Vectors y Titan | Ajusté los parámetros (tamaño, overlap, umbral) y verifiqué el API de S3 Vectors |
| Agente y herramientas | Loop con la Converse API y 4 herramientas con validación | Definí las reglas de negocio de prioridad y esfuerzo y las alineé con el procedimiento |
| Seguridad | Detector de injection, canario, enmascarado de PII y política IAM | Revisé la política IAM recurso por recurso |
| Pruebas | 50 pruebas unitarias y de API, y una suite de evaluación con 15 casos | Diseñé los casos de evaluación y los criterios de aceptación |
| Documentación | Borradores de README, decisiones, guía de consola y riesgos | Corregí y validé cada paso contra la consola real |

## 3. Validaciones realizadas sobre el código generado

1. **Pruebas automatizadas** (`pytest`): 50 pruebas que cubren chunking, validación de entradas, path traversal, detección de injection (positivos y falsos positivos), reglas de herramientas con valores calculados a mano, autenticación, trazabilidad, el handler de Lambda con un evento real de Function URL y los adaptadores de AWS (Bedrock, S3 Vectors, DynamoDB, S3) validados con `botocore.Stubber` contra los modelos de servicio oficiales.
2. **Las pruebas encontraron un bug real en el código generado**: el detector de injection **no detectaba "Muéstrame la API key"**. El patrón usaba `\bmuestra\b` y no cubría la forma con enclítico ("muéstrame"). Se corrigió y quedó la prueba como regresión.
3. **Verificación del API de S3 Vectors contra el modelo de servicio oficial de botocore** (no contra la memoria del asistente): parámetros `vectorBucketName`, `indexName`, `queryVector`, `returnMetadata` y `returnDistance`, y la semántica de distancia coseno = 1 − similitud.
4. **Verificación del paquete Lambda**: se construyó con wheels `manylinux2014_x86_64` para Python 3.13 y se importó de forma aislada para confirmar que carga sin depender del entorno local.
5. **Smoke test de punta a punta** con proveedores offline: ingesta de los 6 documentos (incluido el marcado del documento malicioso), preguntas con fuentes, uso de herramientas, bloqueo de injection e historial.
6. **Evaluación contra Bedrock real** en AWS con `evals/run_eval.py` y LLM-as-judge: 15/15 casos aprobados, precisión de citas del 100 % y groundedness del juez de 4,67/5. No me quedé con el 100 %: revisé caso por caso y documenté problemas que el "aprobado" no mostraba (ver `docs/EVIDENCIA_PRUEBAS.md`).
7. **Validación en el despliegue real.** Varias cosas solo aparecieron al probar en AWS, no en las pruebas locales:
   - **Error 500 al cargar documentos.** Lo diagnostiqué siguiendo el `trace_id` en CloudWatch Logs: el rol IAM no tenía `s3vectors:ListVectors` sobre el ARN real del índice, porque la política tenía un marcador sin reemplazar. Lo corregí con el ARN exacto, sin ampliar permisos con comodines.
   - **El modelo incluía su razonamiento interno** (`<thinking>`) y etiquetas como `<answer>` en la respuesta al usuario. Agregué una limpieza de la salida con su prueba automática.
   - **El agente usaba herramientas de más**, con argumentos inventados en algún caso. Lo documenté como limitación del modelo y propuse mejoras.
8. **Revisión manual** de: la política IAM (mínimo privilegio), que no haya secretos en el código ni en `.env.example`, los mensajes de error (no exponen trazas internas) y las dependencias (versiones fijas).

## 4. Riesgos identificados al usar IA para programar

| Riesgo | Cómo se manifestó o podía manifestarse | Control |
|---|---|---|
| **APIs inventadas o desactualizadas** | Servicios nuevos (S3 Vectors, de 2025) que el modelo podía no conocer bien | Verificación contra el modelo de servicio de boto3 y la documentación oficial |
| **IDs de modelos que cambian** | Nova o Titan con versiones nuevas o IDs con prefijo de inference profile (`us.`) | El ID es configurable por variable de entorno; se verifica en el Model catalog |
| **Seguridad por defecto débil** | Function URL con auth NONE, CORS `*` o permisos IAM amplios, típicos de ejemplos | API key en SSM con fail-closed; IAM por recurso; riesgo documentado con alternativa para producción |
| **Código que "parece" correcto** | El bug del regex de injection | Pruebas con casos positivos y negativos antes de aceptar el código |
| **Supuestos sobre la plataforma** | Se asumió que Bedrock funcionaría al pasar al plan pagado, pero la cuenta nueva tenía las cuotas por modelo en 0 | Se verificó en Service Quotas, se resolvió con AWS Support y, mientras tanto, se probó la infraestructura con proveedores simulados (`fake`/`hash`), cambiando solo variables de entorno |
| **Información sobre costos o planes** | El asistente asumió inicialmente que Bedrock funcionaba en el Free plan; no era así | Verificación en la documentación de AWS y en foros oficiales (re:Post) antes de decidir |
| **Dependencias innecesarias** | Tendencia a sugerir LangChain o frameworks pesados | Se decidió usar un loop propio de unas 80 líneas (D6) |
| **Fuga de datos hacia el asistente** | Pegar secretos o datos reales en el chat de la IA | Solo se usaron datos ficticios; las keys se generaron en CloudShell y nunca se compartieron |

## 5. Cómo evité depender ciegamente de la herramienta

- **Requisitos primero**: el alcance de la prueba (secciones 5.1 a 5.6) se convirtió en una lista de verificación antes de generar código.
- **Pruebas como contrato**: cada componente tiene pruebas con valores esperados calculados a mano (p. ej. `(60 × 1,0 + 8 × 2) × 1,15 = 87 h`).
- **Fuentes primarias**: las afirmaciones sobre servicios, límites y costos se contrastaron con la documentación de AWS.
- **Despliegue manual**: crear cada recurso en la consola obliga a entender qué hace y por qué se necesita cada permiso.
- **Entiendo y puedo explicar cada módulo**: si no podía explicar una línea, la reescribía o la eliminaba.
- **Evaluación cuantitativa**: la calidad del agente se mide con un dataset y métricas, no con la impresión de un par de preguntas.

## 6. Cómo lo usaría en un equipo

- **Kiro o Claude Code** para *spec-driven development*: requisitos → diseño → tareas, con specs versionadas en el repositorio.
- **Revisión de PR asistida**, pero con aprobación humana obligatoria y checks de CI (pruebas, evaluación RAG, SAST como Bandit o Semgrep, y escaneo de secretos).
- Reglas del repositorio (`CLAUDE.md` o `AGENTS.md`) con convenciones, comandos de prueba y prohibiciones, como no tocar IAM sin revisión.
