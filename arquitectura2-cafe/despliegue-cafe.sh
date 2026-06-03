#!/bin/bash
set -e

# ── Variables ─────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
EMAIL="leilagomezvallejo8@gmail.com"
DB_ADMIN_PASSWORD="coffee_beans_for_all"
DB_APP_PASSWORD="coffee"
DB_NAME="COFFEE"
DB_USER="nodeapp"
STACK_NAME="cafe-architecture"
RDS_CLUSTER_ID="supplierdb"
RDS_INSTANCE_ID="supplierdb-instance-1"
ELASTICACHE_ID="mymemcachedsubnet"
BEANSTALK_APP="MyNodeApp"
BEANSTALK_ENV="MyEnv"

printf "\n========================================\n"
printf "  DESPLIEGUE ARQUITECTURA 2 — CAFÉ APP\n"
printf "  Cuenta: ${ACCOUNT_ID}\n"
printf "========================================\n\n"

# ── 1. Desplegar CloudFormation ────────────────────────────
printf "1. Desplegando stack CloudFormation...\n"
aws cloudformation deploy \
  --stack-name $STACK_NAME \
  --template-file cafe-template.yaml \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides DBPassword=$DB_ADMIN_PASSWORD
printf "   Stack desplegado\n"

# Obtener outputs del stack
BUCKET=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --query 'StackResources[?LogicalResourceId==`S3Bucket`].PhysicalResourceId' \
  --output text)
API_ID=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --query 'StackResources[?LogicalResourceId==`ApiGatewayRestApi`].PhysicalResourceId' \
  --output text)
USER_POOL_ID=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --query 'StackResources[?LogicalResourceId==`CognitoUserPool`].PhysicalResourceId' \
  --output text)
CLIENT_ID=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --query 'StackResources[?LogicalResourceId==`CognitoUserPoolClient`].PhysicalResourceId' \
  --output text)
SNS_ARN=$(aws cloudformation describe-stack-resources \
  --stack-name $STACK_NAME \
  --query 'StackResources[?LogicalResourceId==`SNSForSendingEmail`].PhysicalResourceId' \
  --output text)
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/cafe/node-web-app"

printf "   Bucket S3: ${BUCKET}\n"
printf "   API ID: ${API_ID}\n"
printf "   UserPool: ${USER_POOL_ID}\n"

# ── 2. Subir ficheros Lambda y step.json al bucket ─────────
printf "\n2. Subiendo ficheros Lambda y step.json a S3...\n"
aws s3 cp lambdas/generate_html.zip s3://${BUCKET}/generate_html.zip
aws s3 cp lambdas/generate_presigned.zip s3://${BUCKET}/generate_presigned.zip
aws s3 cp lambdas/get_real_data.zip s3://${BUCKET}/get_real_data.zip
aws s3 cp step.json s3://${BUCKET}/step.json
printf "   Ficheros subidos\n"

# Actualizar Lambda generateHTML desde S3
aws lambda update-function-code \
  --function-name generateHTML \
  --s3-bucket $BUCKET \
  --s3-key generate_html.zip > /dev/null

# Actualizar Lambda GeneratePresignedURL desde S3
aws lambda update-function-code \
  --function-name GeneratePresignedURL \
  --s3-bucket $BUCKET \
  --s3-key generate_presigned.zip > /dev/null

# Actualizar Lambda getRealData desde S3
aws lambda update-function-code \
  --function-name getRealData \
  --s3-bucket $BUCKET \
  --s3-key get_real_data.zip > /dev/null

printf "   Lambdas actualizadas con código correcto\n"

# ── 3. Configurar S3 — acceso público y website ────────────
printf "\n3. Configurando S3 y subiendo website...\n"
aws s3api put-public-access-block \
  --bucket $BUCKET \
  --public-access-block-configuration \
    "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

aws s3api put-bucket-policy \
  --bucket $BUCKET \
  --policy "{
    \"Version\": \"2012-10-17\",
    \"Statement\": [{
      \"Effect\": \"Allow\",
      \"Principal\": \"*\",
      \"Action\": \"s3:GetObject\",
      \"Resource\": \"arn:aws:s3:::${BUCKET}/*\"
    }]
  }"

# Subir website (sin config.js — se actualizará después)
aws s3 cp website/ s3://${BUCKET}/ --recursive --exclude "config.js"
printf "   Website subido\n"

# ── 4. Configurar Cognito ──────────────────────────────────
printf "\n4. Configurando Cognito...\n"

# Habilitar USER_PASSWORD_AUTH
aws cognito-idp update-user-pool-client \
  --user-pool-id $USER_POOL_ID \
  --client-id $CLIENT_ID \
  --explicit-auth-flows ALLOW_USER_PASSWORD_AUTH ALLOW_REFRESH_TOKEN_AUTH ALLOW_USER_SRP_AUTH > /dev/null

# Crear usuario cafe_admin
aws cognito-idp admin-create-user \
  --user-pool-id $USER_POOL_ID \
  --username cafe_admin \
  --message-action SUPPRESS \
  --temporary-password "Cafe1234!" 2>/dev/null || printf "   (usuario ya existe)\n"

aws cognito-idp admin-set-user-password \
  --user-pool-id $USER_POOL_ID \
  --username cafe_admin \
  --password "Cafe1234!" \
  --permanent
printf "   Usuario cafe_admin configurado\n"

# ── 5. Suscripción email SNS ───────────────────────────────
printf "\n5. Creando suscripción SNS...\n"
aws sns subscribe \
  --topic-arn $SNS_ARN \
  --protocol email \
  --notification-endpoint $EMAIL > /dev/null
printf "   Suscripción creada (confirmar email)\n"

# ── 6. Crear RDS Aurora MySQL ──────────────────────────────
printf "\n6. Creando RDS Aurora MySQL...\n"

# Obtener VPC y subnets del stack
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=tag:Name,Values=cafe-vpc" \
  --query 'Vpcs[0].VpcId' --output text)

SUBNET1=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[0].SubnetId' --output text)

# Crear security group para RDS
RDS_SG=$(aws ec2 create-security-group \
  --group-name cafe-rds-sg \
  --description "Security group for cafe RDS" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text 2>/dev/null || \
  aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=cafe-rds-sg" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' --output text)

aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG \
  --protocol tcp \
  --port 3306 \
  --cidr 0.0.0.0/0 2>/dev/null || true

# Obtener todas las subnets de la VPC para garantizar cobertura multi-AZ
ALL_SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[*].SubnetId' --output text | tr '\t' ' ')

# Borrar subnet group si existe (puede apuntar a subnets de VPC antigua)
aws rds delete-db-subnet-group \
  --db-subnet-group-name cafe-rds-subnet-group 2>/dev/null || true

# Crear subnet group nuevo con subnets actuales
aws rds create-db-subnet-group \
  --db-subnet-group-name cafe-rds-subnet-group \
  --db-subnet-group-description "Subnet group for cafe RDS" \
  --subnet-ids $ALL_SUBNETS 2>/dev/null || true

# Crear o arrancar cluster Aurora
CLUSTER_STATUS=$(aws rds describe-db-clusters \
  --db-cluster-identifier $RDS_CLUSTER_ID \
  --query 'DBClusters[0].Status' --output text 2>/dev/null || echo "notfound")

if [ "$CLUSTER_STATUS" == "notfound" ] || [ "$CLUSTER_STATUS" == "None" ]; then
  aws rds create-db-cluster \
    --db-cluster-identifier $RDS_CLUSTER_ID \
    --engine aurora-mysql \
    --engine-version 5.7.mysql_aurora.2.11.1 \
    --master-username admin \
    --master-user-password $DB_ADMIN_PASSWORD \
    --database-name $DB_NAME \
    --db-subnet-group-name cafe-rds-subnet-group \
    --vpc-security-group-ids $RDS_SG
  printf "   Cluster RDS creado\n"
elif [ "$CLUSTER_STATUS" == "stopped" ]; then
  aws rds start-db-cluster --db-cluster-identifier $RDS_CLUSTER_ID
  printf "   Cluster RDS arrancado\n"
else
  printf "   (cluster ya existe: $CLUSTER_STATUS)\n"
fi

# Crear o arrancar instancia
INSTANCE_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier $RDS_INSTANCE_ID \
  --query 'DBInstances[0].DBInstanceStatus' --output text 2>/dev/null || echo "notfound")

if [ "$INSTANCE_STATUS" == "notfound" ] || [ "$INSTANCE_STATUS" == "None" ]; then
  aws rds create-db-instance \
    --db-instance-identifier $RDS_INSTANCE_ID \
    --db-instance-class db.t3.small \
    --engine aurora-mysql \
    --db-cluster-identifier $RDS_CLUSTER_ID \
    --no-auto-minor-version-upgrade \
    --publicly-accessible
  printf "   Instancia RDS creada\n"
elif [ "$INSTANCE_STATUS" == "stopped" ]; then
  aws rds start-db-cluster --db-cluster-identifier $RDS_CLUSTER_ID
  printf "   Instancia RDS arrancada\n"
else
  printf "   (instancia ya existe: $INSTANCE_STATUS)\n"
fi

printf "   Esperando a que RDS esté disponible (puede tardar ~5 min)...\n"
aws rds wait db-instance-available --db-instance-identifier $RDS_INSTANCE_ID
printf "   RDS disponible\n"

# Obtener endpoint RDS
RDS_ENDPOINT=$(aws rds describe-db-clusters \
  --db-cluster-identifier $RDS_CLUSTER_ID \
  --query 'DBClusters[0].Endpoint' --output text)
printf "   Endpoint RDS: ${RDS_ENDPOINT}\n"

# ── 7. Cargar schema y datos en RDS ───────────────────────
printf "\n7. Cargando schema y datos en RDS...\n"
mysql -h $RDS_ENDPOINT -P 3306 -u admin -p$DB_ADMIN_PASSWORD \
  -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_APP_PASSWORD}'; GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'%'; FLUSH PRIVILEGES;"

mysql -h $RDS_ENDPOINT -P 3306 -u admin -p$DB_ADMIN_PASSWORD $DB_NAME < coffee_db_dump.sql
printf "   Schema y datos cargados\n"

# ── 8. Actualizar Lambda getRealData con endpoint RDS ──────
printf "\n8. Actualizando Lambda getRealData con endpoint RDS...\n"
aws lambda update-function-configuration \
  --function-name getRealData \
  --environment "Variables={MY_BUCKET_STR=${BUCKET},MY_RD_STR=${RDS_ENDPOINT}}" > /dev/null
printf "   Lambda actualizada\n"

# ── 9. Crear ElastiCache Memcached ─────────────────────────
printf "\n9. Creando ElastiCache Memcached...\n"

# Obtener subnets actuales de la VPC
ALL_SUBNETS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query 'Subnets[*].SubnetId' --output text | tr '\t' ' ')

# Borrar subnet group si existe (puede apuntar a subnets de VPC antigua)
aws elasticache delete-cache-subnet-group \
  --cache-subnet-group-name mymemcachedsubnet 2>/dev/null || true

# Crear subnet group nuevo con subnets actuales
aws elasticache create-cache-subnet-group \
  --cache-subnet-group-name mymemcachedsubnet \
  --cache-subnet-group-description "Subnet group for cafe Memcached" \
  --subnet-ids $ALL_SUBNETS 2>/dev/null || true

# Crear cluster Memcached si no existe
MEMC_STATUS=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id $ELASTICACHE_ID \
  --query 'CacheClusters[0].CacheClusterStatus' --output text 2>/dev/null || echo "notfound")

if [ "$MEMC_STATUS" == "notfound" ] || [ "$MEMC_STATUS" == "None" ]; then
  aws elasticache create-cache-cluster \
    --cache-cluster-id $ELASTICACHE_ID \
    --cache-node-type cache.t3.micro \
    --engine memcached \
    --num-cache-nodes 1 \
    --cache-subnet-group-name mymemcachedsubnet
  printf "   Cluster Memcached creado\n"
else
  printf "   (cluster ya existe: $MEMC_STATUS)\n"
fi

printf "   Esperando a que ElastiCache esté disponible...\n"
aws elasticache wait cache-cluster-available --cache-cluster-id $ELASTICACHE_ID
MEMC_ENDPOINT=$(aws elasticache describe-cache-clusters \
  --cache-cluster-id $ELASTICACHE_ID \
  --show-cache-node-info \
  --query 'CacheClusters[0].CacheNodes[0].Endpoint.Address' --output text)
MEMC_HOST="${MEMC_ENDPOINT}:11211"
printf "   ElastiCache disponible: ${MEMC_HOST}\n"

# ── 10. Construir y subir imagen Docker a ECR ──────────────
printf "\n10. Construyendo imagen Docker...\n"
cd docker/codebase_partner

# Actualizar Dockerfile a Node 18
sed -i 's/node:11-alpine/node:18-alpine/g' Dockerfile

# Login ECR
aws ecr get-login-password --region $REGION | \
  docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com

docker build --tag cafe/node-web-app . --quiet
docker tag cafe/node-web-app:latest ${ECR_URI}:latest
docker push ${ECR_URI}:latest --quiet
cd ~/arquitectura2-cafe
printf "   Imagen subida a ECR\n"

# ── 11. Crear Dockerrun.aws.json y subir a S3 ──────────────
printf "\n11. Actualizando Dockerrun.aws.json...\n"
cat > docker/Dockerrun.aws.json << EOF
{
  "AWSEBDockerrunVersion": "1",
  "Image": {
    "Name": "${ECR_URI}:latest",
    "Update": "true"
  },
  "Ports": [
    {
      "ContainerPort": 3000
    }
  ]
}
EOF
aws s3 cp docker/Dockerrun.aws.json s3://${BUCKET}/Dockerrun.aws.json
printf "   Dockerrun.aws.json actualizado\n"

# ── 12. Crear entorno Elastic Beanstalk ────────────────────
printf "\n12. Creando entorno Elastic Beanstalk...\n"

SOLUTION_STACK=$(aws elasticbeanstalk list-available-solution-stacks \
  --query 'SolutionStacks[?contains(@, `Amazon Linux 2023`) && contains(@, `Docker`)] | [0]' \
  --output text)

# Crear versión de la aplicación
VERSION_LABEL="v$(date +%Y%m%d%H%M%S)"
aws elasticbeanstalk create-application-version \
  --application-name $BEANSTALK_APP \
  --version-label $VERSION_LABEL \
  --source-bundle S3Bucket=${BUCKET},S3Key=Dockerrun.aws.json 2>/dev/null || true

ENV_STATUS=$(aws elasticbeanstalk describe-environments \
  --environment-names $BEANSTALK_ENV \
  --query 'Environments[0].Status' --output text 2>/dev/null || echo "notfound")

if [ "$ENV_STATUS" == "notfound" ] || [ "$ENV_STATUS" == "None" ] || [ "$ENV_STATUS" == "Terminated" ]; then
  aws elasticbeanstalk create-environment \
    --application-name $BEANSTALK_APP \
    --environment-name $BEANSTALK_ENV \
    --version-label $VERSION_LABEL \
    --solution-stack-name "$SOLUTION_STACK" \
    --option-settings \
      Namespace=aws:autoscaling:launchconfiguration,OptionName=IamInstanceProfile,Value=LabInstanceProfile \
      Namespace=aws:ec2:vpc,OptionName=VPCId,Value=$VPC_ID \
      Namespace=aws:ec2:vpc,OptionName=Subnets,Value=$SUBNET1 \
      Namespace=aws:ec2:vpc,OptionName=ELBSubnets,Value=$SUBNET1 \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=APP_DB_HOST,Value=$RDS_ENDPOINT \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=APP_DB_USER,Value=$DB_USER \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=APP_DB_PASSWORD,Value=$DB_APP_PASSWORD \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=APP_DB_NAME,Value=$DB_NAME \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=MEMC_HOST,Value=$MEMC_HOST \
      Namespace=aws:elasticbeanstalk:application:environment,OptionName=SQS_ENDPOINT,Value=https://sqs.${REGION}.amazonaws.com/${ACCOUNT_ID}/cafe-inventory-updates
  printf "   Entorno Beanstalk creado\n"
else
  printf "   (entorno ya existe: $ENV_STATUS)\n"
fi

if [ "$ENV_STATUS" == "notfound" ] || [ "$ENV_STATUS" == "None" ] || [ "$ENV_STATUS" == "Terminated" ]; then
  printf "   Esperando a que Beanstalk esté listo...\n"
  aws elasticbeanstalk wait environment-updated --environment-names $BEANSTALK_ENV
fi
BEANSTALK_URL=$(aws elasticbeanstalk describe-environments \
  --environment-names $BEANSTALK_ENV \
  --query 'Environments[0].CNAME' --output text)
printf "   Beanstalk listo: http://${BEANSTALK_URL}\n"

# ── 13. Crear y asociar WAF ────────────────────────────────
printf "\n13. Creando WAF...\n"
WAF_ARN=$(aws wafv2 list-web-acls --scope REGIONAL \
  --query "WebACLs[?Name=='cafe-waf'].ARN" --output text)

if [ -z "$WAF_ARN" ]; then
  WAF_ARN=$(aws wafv2 create-web-acl \
    --name cafe-waf \
    --scope REGIONAL \
    --default-action Allow={} \
    --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=cafe-waf \
    --rules '[]' \
    --region $REGION \
    --query 'Summary.ARN' --output text)
fi

LOCK_TOKEN=$(aws wafv2 get-web-acl \
  --name cafe-waf \
  --scope REGIONAL \
  --id $(echo $WAF_ARN | cut -d'/' -f4) \
  --query 'LockToken' --output text)

aws wafv2 update-web-acl \
  --name cafe-waf \
  --scope REGIONAL \
  --id $(echo $WAF_ARN | cut -d'/' -f4) \
  --lock-token $LOCK_TOKEN \
  --default-action Allow={} \
  --visibility-config SampledRequestsEnabled=true,CloudWatchMetricsEnabled=true,MetricName=cafe-waf \
  --rules '[{"Name":"AWSManagedRulesCommonRuleSet","Priority":1,"OverrideAction":{"None":{}},"Statement":{"ManagedRuleGroupStatement":{"VendorName":"AWS","Name":"AWSManagedRulesCommonRuleSet"}},"VisibilityConfig":{"SampledRequestsEnabled":true,"CloudWatchMetricsEnabled":true,"MetricName":"AWSManagedRulesCommonRuleSet"}}]' > /dev/null

printf "   Asociando WAF a API Gateway (esperando disponibilidad)...\n"
for i in 1 2 3; do
  aws wafv2 associate-web-acl \
    --web-acl-arn $WAF_ARN \
    --resource-arn arn:aws:apigateway:${REGION}::/restapis/${API_ID}/stages/prod 2>/dev/null && break
  printf "   Reintento $i...\n"
  sleep 10
done
printf "   WAF creado y asociado a API Gateway\n"

# ── 14. Subir código a CodeCommit ──────────────────────────
printf "\n14. Subiendo código a CodeCommit...\n"
git config --global credential.helper '!aws codecommit credential-helper $@'
git config --global credential.UseHttpPath true
git config --global user.email "cafe_admin@cafe.com"
git config --global user.name "Cafe Admin"

REPO_URL="https://git-codecommit.${REGION}.amazonaws.com/v1/repos/front_end_website"
rm -rf /tmp/cafe-repo
git clone $REPO_URL /tmp/cafe-repo
cp website/* /tmp/cafe-repo/ 2>/dev/null || true
cp -r website/images /tmp/cafe-repo/ 2>/dev/null || true
cp -r website/scripts /tmp/cafe-repo/ 2>/dev/null || true
cp -r website/styles /tmp/cafe-repo/ 2>/dev/null || true
cd /tmp/cafe-repo
git add .
git commit -m "Initial commit - cafe website" 2>/dev/null || true
git push 2>/dev/null || true
cd ~/arquitectura2-cafe
printf "   Código subido a CodeCommit\n"

# ── 15. Actualizar config.js con valores reales ────────────
printf "\n15. Actualizando config.js...\n"
API_URL="https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod"
COGNITO_DOMAIN=$(aws cognito-idp describe-user-pool \
  --user-pool-id $USER_POOL_ID \
  --query 'UserPool.Domain' --output text)

cat > /tmp/config.js << EOF
window.COFFEE_CONFIG = {
        API_GW_BASE_URL_STR: "https://${API_ID}.execute-api.${REGION}.amazonaws.com/prod",
        COGNITO_LOGIN_BASE_URL_STR: "https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/login?client_id=${CLIENT_ID}&response_type=token&scope=email+openid&redirect_uri=http://${BUCKET}.s3-website-${REGION}.amazonaws.com/callback.html"
};
EOF

aws s3 cp /tmp/config.js s3://${BUCKET}/config.js
printf "   config.js actualizado\n"

# ── 16. Seed de productos en DynamoDB ─────────────────────
printf "\n16. Insertando productos en DynamoDB...\n"
python3 << 'EOF'
import boto3, json
from decimal import Decimal

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
table = dynamodb.Table('FoodProducts')

with open('website/all_products.json') as f:
    data = json.load(f, parse_float=Decimal)

products = data['product_item_arr']
for product in products:
    product['product_name'] = product.pop('product_name_str')
    product['description'] = product.pop('description_str')
    product['tags'] = product.pop('tag_str_arr')
    product['price_in_cents'] = product.pop('price_in_cents_int')
    if 'special_int' in product:
        product['special'] = product.pop('special_int')
    if 'product_id_str' in product:
        product['product_id'] = product.pop('product_id_str')
    table.put_item(Item=product)

print(f"Insertados {len(products)} productos")
EOF
printf "   Productos insertados en DynamoDB\n"

# ── Resumen final ──────────────────────────────────────────
printf "\n\n========================================\n"
printf "  DESPLIEGUE COMPLETADO\n"
printf "========================================\n\n"
printf "Website S3:     http://${BUCKET}.s3-website-${REGION}.amazonaws.com\n"
printf "API Gateway:    ${API_URL}\n"
printf "Beanstalk:      http://${BEANSTALK_URL}\n"
printf "RDS Endpoint:   ${RDS_ENDPOINT}\n"
printf "ElastiCache:    ${MEMC_HOST}\n"
printf "\n⚠️  Recuerda confirmar la suscripción SNS en tu email\n"
printf "⚠️  Recuerda conceder permisos a nodeapp en RDS si es necesario\n\n"
