#!/bin/bash
set -e

# ── Variables ─────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
LAMBDA_CODE_BUCKET="gamestore-lambda-code-${ACCOUNT_ID}"
SWAGGER_FILE="swagger/swagger-config.yaml"

printf "\n========================================\n"
printf "  DESPLIEGUE ARQUITECTURA 1 — GAME STORE\n"
printf "  Cuenta: ${ACCOUNT_ID}\n"
printf "========================================\n\n"

# ── 1. S3 ──────────────────────────────────────────────────
printf "Creando buckets S3...\n"
aws cloudformation deploy \
  --stack-name gamestore-s3 \
  --template-file stacks/s3-stack.yaml
printf "Buckets S3 creados\n"

# ── 2. DynamoDB ────────────────────────────────────────────
printf "Creando tablas DynamoDB...\n"
aws cloudformation deploy \
  --stack-name gamestore-dynamodb \
  --template-file stacks/dynamodb-stack.yaml
printf "Tablas DynamoDB creadas\n"

# ── 3. Mensajería ──────────────────────────────────────────
printf "Creando colas SQS y topic SNS...\n"
aws cloudformation deploy \
  --stack-name gamestore-messaging \
  --template-file stacks/messaging-stack.yaml
printf "Mensajería creada\n"

# ── 4. Empaquetar y subir Lambdas ──────────────────────────
printf "Empaquetando Lambdas...\n"
chmod -R u+w lambdas/ swagger/
for lambda in PedidosHandler TareasHandler ProcesarPedido ComprobarDisponibilidad GamesHandler UsersHandler CategoriesHandler TagsHandler; do
  zip -j lambdas/${lambda}.zip lambdas/${lambda}.py
  aws s3 cp lambdas/${lambda}.zip s3://${LAMBDA_CODE_BUCKET}/${lambda}.zip
  printf "  ${lambda} subido\n"
done
printf "Lambdas empaquetadas y subidas\n"

# ── 5. Lambdas ─────────────────────────────────────────────
printf "Desplegando Lambdas...\n"
aws cloudformation deploy \
  --stack-name gamestore-lambdas \
  --template-file stacks/lambda-stack.yaml \
  --capabilities CAPABILITY_IAM
printf "Lambdas desplegadas\n"

# ── 6. API Gateway ─────────────────────────────────────────
printf "Desplegando API Gateway...\n"
aws cloudformation deploy \
  --stack-name gamestore-apigateway \
  --template-file stacks/apigateway-stack.yaml
printf "API Gateway desplegada\n"

# ── 7. Actualizar swagger-config.yaml ──────────────────────
printf "Actualizando swagger-config.yaml...\n"
API_URL=$(aws cloudformation describe-stacks \
  --stack-name gamestore-apigateway \
  --query "Stacks[0].Outputs[?OutputKey=='ApiUrl'].OutputValue" \
  --output text)

sed -i -E "s|url: https://[^/]+\.execute-api\.[^/]+\.amazonaws\.com/prod|url: ${API_URL}|g" ${SWAGGER_FILE}
printf "URL actualizada a: ${API_URL}\n"

# ── 8. Subir Swagger a S3 ──────────────────────────────────
printf "Subiendo Swagger UI a S3...\n"
SWAGGER_BUCKET="gamestore-swagger-${ACCOUNT_ID}"
aws s3 cp swagger/ s3://${SWAGGER_BUCKET}/ --recursive
printf "Swagger subido\n"

# ── 9. Seed de datos iniciales ─────────────────────────────
printf "Insertando datos iniciales...\n"
python3 lambdas/SeedData.py
printf "Datos insertados\n"

# ── Resumen final ──────────────────────────────────────────
printf "\n\n========================================\n"
printf "  DESPLIEGUE COMPLETADO\n"
printf "========================================\n\n"
printf "API URL: ${API_URL}\n"
printf "Swagger URL: http://${SWAGGER_BUCKET}.s3-website-${REGION}.amazonaws.com\n"
