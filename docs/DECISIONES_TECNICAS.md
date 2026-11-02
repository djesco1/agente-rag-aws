# Decisiones técnicas

Este documento resume las decisiones de arquitectura, las alternativas evaluadas y por qué se eligió cada opción. El criterio general fue construir **la solución más simple que cumpla el alcance y sea defendible en producción**, con costo cercano a cero para la prueba.

## Referencias usadas

- AWS Prescriptive Guidance, *Retrieval Augmented Generation options and architectures on AWS*.
- AWS Builder Center, *Architecting Serverless RAG on AWS: From Ingestion to Retrieval*: chunks de tamaño medio con 10-20 % de overlap, umbral de similitud, roles separados.
- Arquitectura de referencia comunitaria *Lambda + Bedrock (Nova + Titan V2) + S3 Vectors*: patrón muy cercano al elegido.
- AWS Builder Center, *Build a tool use based agent loop with Amazon Bedrock* (Converse API).
- AWS Well-Architected Generative AI Lens, **GENSEC04-BP02**: sanitizar y validar entradas, límites de contexto en el prompt, validación por capas.

## Resumen de decisiones

| # | Decisión | Alternativas consideradas | Por qué |
|---|---|---|---|
| D1 | **FastAPI** sobre **AWS Lambda** con **Function URL** (Mangum) | Flask; ECS Fargate; API Gateway | FastAPI da validación con Pydantic y documentación OpenAPI/Swagger automática (requisito de documentación de la API). Lambda escala a cero y entra en la capa gratuita. La Function URL evita configurar API Gateway para una prueba. Fargate cobra por hora encendido. |
| D2 | **Amazon Bedrock con Nova Lite** como LLM (Converse API) | Claude en Bedrock; Azure OpenAI; modelo local | Nova es un modelo propio de Amazon: no requiere suscripción de Marketplace, es de bajo costo y soporta tool use nativo. La Converse API es uniforme entre modelos, así que cambiar a Claude o Llama es cambiar `LLM_MODEL_ID`. |
| D3 | **Titan Text Embeddings V2** (1024 dimensiones, normalizado) | Cohere Embed; embeddings locales | Es multilingüe (los documentos están en español), tiene costo muy bajo y no requiere Marketplace. 1024 dimensiones da mejor recuperación que 256/512 con un costo de almacenamiento despreciable a esta escala. |
| D4 | **Amazon S3 Vectors** como vector store | OpenSearch Serverless; Aurora pgvector; FAISS/Chroma en Lambda | OpenSearch Serverless y Aurora cobran capacidad mínima aunque no se usen. FAISS en Lambda exige recargar el índice en cada cold start y no es compartido. S3 Vectors es serverless, de pago por uso, durable y se consulta con un API simple. Contra: menos funciones de búsqueda (no tiene búsqueda híbrida BM25); ver mejoras futuras. |
| D5 | **RAG propio** (ingesta, chunking, recuperación) en vez de Bedrock Knowledge Bases | Bedrock Knowledge Bases | Knowledge Bases resuelve todo, pero oculta el pipeline. La prueba evalúa la implementación RAG (20 %), así que se implementa explícitamente y queda controlable: tamaño de chunk, umbral, citas, marcado de chunks sospechosos. En producción, Knowledge Bases es una alternativa válida para reducir código. |
| D6 | **Agente con loop propio** sobre Converse (sin LangChain, LlamaIndex ni Strands) | LangChain/LangGraph; Strands Agents; Bedrock Agents | Son unas 80 líneas fáciles de auditar y explicar, con pocas dependencias (paquete de 18 MB y cold start más corto). Control total de límites: máximo de pasos, allowlist de herramientas y validación de argumentos. Para agentes multi-paso complejos se migraría a Strands o LangGraph. |
| D7 | **Recuperación siempre antes del agente**, más herramientas | RAG como herramienta que el modelo decide invocar | Garantiza que cada respuesta tenga contexto documental y reduce las alucinaciones en modelos pequeños. Las herramientas cubren datos estructurados (solicitudes) y reglas deterministas (prioridad y esfuerzo). |
| D8 | **Herramientas deterministas** con reglas copiadas de los documentos | Que el LLM "calcule" la prioridad o el esfuerzo | Un LLM no debe hacer aritmética de negocio. Las reglas en código son testeables (pruebas unitarias) y coinciden con el procedimiento documentado, así que RAG y herramienta dan la misma respuesta. |
| D9 | **DynamoDB** para historial y solicitudes | RDS; archivos JSON en S3 | Es serverless, tiene capa gratuita, latencia de milisegundos y no requiere VPC. El historial usa `pk="HISTORY"` y `sk="<timestamp>#<trace_id>"` para listar "las últimas N" con un solo Query. |
| D10 | **API key en SSM Parameter Store (SecureString)** | Secrets Manager; variable de entorno en texto plano | El tier Standard de Parameter Store es gratis y cifra con KMS. Secrets Manager cuesta 0,40 USD al mes por secreto y aporta rotación automática, que no se necesita en la prueba. La key no se guarda en el código ni en las variables. |
| D11 | **Proveedores intercambiables por variable de entorno** | Código acoplado a Bedrock | Permite correr las pruebas offline (`fake`/`hash`) y cambiar de modelo o de nube (Azure OpenAI sería un proveedor más) sin tocar el agente. Se validó en la práctica: mientras Bedrock tuvo las cuotas en 0, la infraestructura se probó con `fake`/`hash` y luego se pasó a Bedrock cambiando solo variables de entorno. |
| D12 | **Logging JSON a stdout** con `trace_id` | X-Ray/OpenTelemetry desde el día 1 | CloudWatch indexa el JSON automáticamente y Logs Insights permite consultar por campo. Es simple y suficiente. OpenTelemetry/X-Ray queda en mejoras futuras. |
| D13 | **Guardrails por capas en código** | Solo Bedrock Guardrails | Capa 1: detector heurístico (rápido y sin costo). Capa 2: prompt con jerarquía y documentos tratados como datos. Capa 3: token canario en la salida. Bedrock Guardrails se recomienda para producción (ver RIESGOS_Y_PRODUCCION.md), pero se dejó fuera para mantener costo y complejidad bajos. |
| D14 | **Despliegue manual por consola** documentado paso a paso | SAM/CDK/Terraform | Es un requisito personal del candidato para dominar cada recurso. En producción se usaría IaC (ver mejoras futuras). |

## Parámetros RAG

| Parámetro | Valor | Justificación |
|---|---|---|
| `CHUNK_SIZE` | 800 caracteres (~200 tokens) | Los documentos son procedimientos con secciones cortas. Fragmentos pequeños dan citas más precisas. |
| `CHUNK_OVERLAP` | 120 (15 %) | Está dentro del rango recomendado de 10-20 %. Evita perder ideas en el borde de un fragmento. |
| Chunking | Por sección Markdown, luego párrafo y luego oración | Cada fragmento conserva la ruta de su sección, que se usa en el embedding y en la cita. |
| `TOP_K` | 4 | Balancea el contexto suficiente con el costo de tokens. |
| `MIN_RELEVANCE` | 0,20 coseno | Si ningún fragmento supera el umbral, el modelo recibe "sin documentos" y debe declarar falta de información. Se calibra con los puntajes registrados en los logs. |
| Temperatura | 0,1 | Respuestas consistentes y fieles al contexto. |

## Flujo de una pregunta

1. Se validan la API key y la entrada (Pydantic: longitud, formato de `session_id`).
2. El guardrail de entrada evalúa prompt injection. Si lo detecta, responde sin llamar al modelo.
3. Se genera el embedding de la pregunta (Titan V2) y se ejecuta `QueryVectors` (top-4). Se filtra por umbral.
4. El prompt incluye los fragmentos entre etiquetas `<documento ref="n">`. Los marcados como sospechosos llevan el atributo `sospechoso="true"`.
5. Loop del agente (máximo 5 pasos): Converse con `toolConfig`. Si el modelo pide una herramienta, se valida contra la allowlist y con Pydantic, se ejecuta y el resultado vuelve al modelo.
6. El guardrail de salida revisa el token canario y se extraen las citas `[n]`, que se convierten en la lista de fuentes.
7. Se guarda la traza en DynamoDB y el log `ask_completed` en CloudWatch.
