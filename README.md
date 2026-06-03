# Arquitecturas AWS — TFG Monitorización de Microservicios

Este repositorio contiene el código de despliegue de las dos arquitecturas cloud desarrolladas como caso de estudio en el Trabajo de Fin de Grado *"Monitorización y análisis de arquitecturas cloud basadas en microservicios"*.

**Autora:** Leila Gómez Vallejo  
**Grado:** Ingeniería Informática — ETSI Informáticos, UPM

---

## Requisitos previos

- Acceso a **AWS Academy Learner Lab** con sesión activa
- Las arquitecturas están diseñadas para desplegarse íntegramente desde **AWS CloudShell**
- No se requiere instalación de herramientas adicionales; CloudShell incluye AWS CLI y Python

---

## Arquitectura 1 — Game Store Serverless

Arquitectura exclusivamente serverless que implementa una tienda de videojuegos. Compuesta por funciones Lambda, tablas DynamoDB, una API REST en API Gateway, colas SQS con DLQ, un topic SNS y almacenamiento S3 para el código y la interfaz Swagger.

### Estructura

```
arquitectura1-serverless/
├── stacks/          # Plantillas CloudFormation (5 stacks)
├── lambdas/         # Código fuente de las funciones Lambda
├── swagger/         # Archivos de la interfaz Swagger UI
└── despliegue.sh    # Script de despliegue automatizado
```

### Despliegue

1. Inicia sesión en AWS Academy Learner Lab y abre **CloudShell**.

2. Sube el fichero `arquitectura1-serverless.zip` usando el botón **Actions → Upload file** de CloudShell.

3. Ejecuta los siguientes comandos:

```bash
unzip arquitectura1-serverless.zip
chmod -R u+w ~/arquitectura1-serverless/
cd ~/arquitectura1-serverless
chmod +x despliegue.sh
./despliegue.sh
```

4. Al finalizar, el script mostrará en pantalla la URL de la API y la URL de Swagger UI.

### Proceso de despliegue

El script orquesta la creación de los recursos en el siguiente orden:

1. Creación de los buckets S3
2. Creación de las tablas DynamoDB
3. Creación de las colas SQS, DLQ y topic SNS
4. Empaquetado y subida del código Lambda a S3
5. Despliegue de las funciones Lambda con sus variables de entorno y triggers
6. Despliegue de API Gateway con todos sus recursos, métodos e integraciones
7. Actualización de la configuración de Swagger UI y subida al bucket S3
8. Inserción de datos iniciales en DynamoDB

---

## Arquitectura 2 — Café App

Arquitectura híbrida que combina servicios serverless con servicios PaaS. Implementa una aplicación de gestión de un café con autenticación, base de datos relacional, caché, orquestación de flujos y seguridad perimetral.

### Estructura

```
arquitectura2-cafe/
├── lambdas/              # Código fuente de las funciones Lambda
├── docker/               # Dockerfile e imagen de la aplicación web
├── website/              # Código fuente del sitio web frontend
├── cafe-template.yaml    # Plantilla CloudFormation (infraestructura base)
├── coffee_db_dump.sql    # Esquema y datos iniciales de la base de datos
├── step.json             # Definición de la máquina de estados Step Functions
└── despliegue-cafe.sh    # Script de despliegue automatizado
```

### Despliegue

1. Inicia sesión en AWS Academy Learner Lab y abre **CloudShell**.

2. Sube el fichero `arquitectura2-cafe.zip` usando el botón **Actions → Upload file** de CloudShell.

3. Ejecuta los siguientes comandos:

```bash
unzip arquitectura2-cafe.zip
chmod -R u+w ~/arquitectura2-cafe/
cd ~/arquitectura2-cafe
chmod +x despliegue-cafe.sh
./despliegue-cafe.sh
```

4. El proceso tarda aproximadamente 10-15 minutos debido a la creación del clúster RDS y el entorno Elastic Beanstalk.

### Proceso de despliegue

El script combina el despliegue de la plantilla CloudFormation con llamadas directas a la AWS CLI para los servicios que no pueden incluirse en la plantilla por restricciones del entorno Learner Lab:

1. Despliegue del stack CloudFormation con la infraestructura base (Lambda, DynamoDB, API Gateway, Cognito, Step Functions, SNS, SQS, ECR, CodeCommit, S3, Elastic Beanstalk)
2. Subida del código Lambda a S3 y actualización de las funciones
3. Configuración del bucket S3 con acceso público y subida del sitio web
4. Configuración de Cognito y creación del usuario administrador
5. Creación de la suscripción de correo electrónico en SNS
6. Creación del clúster RDS mediante CLI
7. Carga del esquema y datos iniciales en RDS
8. Actualización de la función Lambda con el endpoint de RDS
9. Creación del clúster ElastiCache mediante CLI
10. Construcción de la imagen Docker y subida a ECR
11. Creación del entorno Elastic Beanstalk con las variables de entorno
12. Creación de la Web ACL de WAF y asociación a API Gateway
13. Subida del código fuente a CodeCommit
14. Generación del fichero de configuración con las URLs reales y subida a S3
15. Inserción del catálogo de productos en DynamoDB

---
