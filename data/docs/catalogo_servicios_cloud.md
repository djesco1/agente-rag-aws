# Catálogo de servicios cloud recomendados y lineamientos de modernización

Documento: ARQ-CLD-003 · Versión 1.3 · Dueño: Arquitectura Empresarial

## 1. Principios

1. **Servicios administrados primero**: se prefieren servicios administrados (PaaS o serverless) sobre máquinas virtuales.
2. **Multi-nube por equivalencia**: el proveedor principal es AWS y Azure es el alterno. Cada patrón debe tener su equivalente documentado en ambas nubes.
3. **Seguridad por defecto**: cifrado en reposo y en tránsito, secretos en un gestor administrado y acceso con identidades (roles), no con llaves estáticas.
4. **Costo visible**: todo recurso lleva las etiquetas proyecto, ambiente y centro-de-costo, y cada cuenta tiene alertas de presupuesto.

## 2. Servicios aprobados por necesidad

| Necesidad | AWS | Azure |
|---|---|---|
| Cómputo serverless y APIs | Lambda, API Gateway | Azure Functions, API Management |
| Contenedores | ECS con Fargate, EKS | Container Apps, AKS |
| Base de datos relacional | RDS o Aurora PostgreSQL | Azure Database for PostgreSQL |
| Base de datos NoSQL | DynamoDB | Cosmos DB |
| Almacenamiento de objetos | S3 | Blob Storage |
| Mensajería y eventos | SQS, SNS, EventBridge | Service Bus, Event Grid |
| IA generativa | Amazon Bedrock | Azure OpenAI o AI Foundry |
| Búsqueda vectorial | S3 Vectors, OpenSearch | Azure AI Search |
| Observabilidad | CloudWatch, X-Ray | Azure Monitor, Application Insights |
| Secretos | Secrets Manager, SSM Parameter Store | Key Vault |
| Orquestación | Step Functions | Logic Apps |

## 3. Estrategias de migración (las 6R)

- **Rehost**: mover sin cambios, por ejemplo de una máquina virtual a EC2.
- **Replatform**: hacer cambios mínimos para aprovechar un servicio administrado, por ejemplo pasar de Oracle a RDS PostgreSQL o llevar la aplicación a contenedores.
- **Refactor**: rediseñar hacia una arquitectura nativa de nube, con microservicios o serverless.
- **Repurchase**: reemplazar por un producto SaaS.
- **Retain**: mantener la aplicación en sitio por ahora.
- **Retire**: dar de baja la aplicación.

Para aplicaciones Java monolíticas con frameworks fuera de soporte, el lineamiento es usar **Replatform** a contenedores como primer paso y luego **Refactor** incremental con el patrón *strangler fig*.

## 4. Criterios para iniciativas de IA generativa

- Se usan modelos disponibles en Amazon Bedrock o en Azure OpenAI dentro de la cuenta corporativa.
- Toda solución de IA debe usar RAG con fuentes citadas, guardrails contra prompt injection y registro de interacciones.
- Antes de pasar a producción se exige una evaluación con un conjunto de preguntas de prueba y criterios de aceptación.
