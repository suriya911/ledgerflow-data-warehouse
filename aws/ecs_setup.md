# AWS ECS Fargate Setup — Step 8d

Run these commands after RDS (8a), S3 (8b), and ECR (8c) are done.
Replace `<account-id>` and `<region>` with your actual values.

---

## Prerequisites

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="us-east-1"
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" --output text)
```

---

## 1. Create IAM roles

### Execution role (allows ECS to pull from ECR and write to CloudWatch)

```bash
# Create the execution role
aws iam create-role \
  --role-name ledgerflow-ecs-execution-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach AWS-managed policies for ECR pull + CloudWatch logs
aws iam attach-role-policy \
  --role-name ledgerflow-ecs-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Allow reading secrets from Secrets Manager (for DATABASE_URL injection)
aws iam put-role-policy \
  --role-name ledgerflow-ecs-execution-role \
  --policy-name SecretsAccess \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": "arn:aws:secretsmanager:'$REGION':'$ACCOUNT_ID':secret:ledgerflow/*"
    }]
  }'
```

### Task role (what the running container can DO — S3 writes, RDS connect)

```bash
aws iam create-role \
  --role-name ledgerflow-ecs-task-role \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [{
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }]
  }'

# Attach the custom policy from aws/iam_policy.json
# First create the policy, then attach
aws iam create-policy \
  --policy-name ledgerflow-pipeline-policy \
  --policy-document file://aws/iam_policy.json

aws iam attach-role-policy \
  --role-name ledgerflow-ecs-task-role \
  --policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/ledgerflow-pipeline-policy
```

---

## 2. Create CloudWatch log group

```bash
aws logs create-log-group \
  --log-group-name /ecs/ledgerflow-airflow \
  --region $REGION

# Retain logs for 30 days (reduce cost)
aws logs put-retention-policy \
  --log-group-name /ecs/ledgerflow-airflow \
  --retention-in-days 30
```

---

## 3. Create Airflow secret

```bash
# Airflow needs a random secret key for session signing
AIRFLOW_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")

aws secretsmanager create-secret \
  --name ledgerflow/airflow \
  --description "Airflow webserver secret key" \
  --secret-string "{\"SECRET_KEY\": \"$AIRFLOW_SECRET\"}"
```

---

## 4. Register the ECS task definition

```bash
# First replace placeholders in the JSON
sed -e "s/<account-id>/$ACCOUNT_ID/g" \
    -e "s/<region>/$REGION/g" \
    aws/ecs_task_definition.json > /tmp/ecs_task_def.json

aws ecs register-task-definition \
  --cli-input-json file:///tmp/ecs_task_def.json
```

---

## 5. Create ECS cluster and service

```bash
# Create the cluster (Fargate clusters have no EC2 instances to manage)
aws ecs create-cluster \
  --cluster-name ledgerflow-cluster \
  --capacity-providers FARGATE \
  --default-capacity-provider-strategy capacityProvider=FARGATE,weight=1

# Create a security group for ECS tasks
ECS_SG_ID=$(aws ec2 create-security-group \
  --group-name ledgerflow-ecs-sg \
  --description "LedgerFlow ECS tasks" \
  --vpc-id $VPC_ID \
  --query GroupId --output text)

# Allow inbound HTTP on 8080 (Airflow UI)
aws ec2 authorize-security-group-ingress \
  --group-id $ECS_SG_ID \
  --protocol tcp \
  --port 8080 \
  --cidr 0.0.0.0/0   # Restrict to your IP for tighter security

# Allow ECS to reach RDS (update the RDS security group to allow from ECS SG)
RDS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=ledgerflow-rds-sg" \
  --query "SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG_ID \
  --protocol tcp \
  --port 5432 \
  --source-group $ECS_SG_ID

# Get a subnet for the service (pick any public subnet for public IP)
SUBNET_ID=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" "Name=mapPublicIpOnLaunch,Values=true" \
  --query "Subnets[0].SubnetId" --output text)

# Initialize Airflow DB before starting the service
aws ecs run-task \
  --cluster ledgerflow-cluster \
  --task-definition ledgerflow-airflow \
  --launch-type FARGATE \
  --overrides '{"containerOverrides":[{"name":"airflow-webserver","command":["db","init"]}]}' \
  --network-configuration "awsvpcConfiguration={
    subnets=[$SUBNET_ID],
    securityGroups=[$ECS_SG_ID],
    assignPublicIp=ENABLED
  }"

echo "Waiting for db init task to complete (~30 seconds)..."
sleep 40

# Create the long-running ECS service (1 task, stays up permanently)
aws ecs create-service \
  --cluster ledgerflow-cluster \
  --service-name ledgerflow-airflow \
  --task-definition ledgerflow-airflow \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={
    subnets=[$SUBNET_ID],
    securityGroups=[$ECS_SG_ID],
    assignPublicIp=ENABLED
  }"

echo "ECS service created. Waiting for task to start..."
aws ecs wait services-stable \
  --cluster ledgerflow-cluster \
  --services ledgerflow-airflow
```

---

## 6. Get the Airflow UI URL

```bash
# Find the public IP of the running task
TASK_ARN=$(aws ecs list-tasks \
  --cluster ledgerflow-cluster \
  --service-name ledgerflow-airflow \
  --query "taskArns[0]" --output text)

ENI_ID=$(aws ecs describe-tasks \
  --cluster ledgerflow-cluster \
  --tasks $TASK_ARN \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value" \
  --output text)

PUBLIC_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --query "NetworkInterfaces[0].Association.PublicIp" \
  --output text)

echo "Airflow UI: http://$PUBLIC_IP:8080"
echo "Login: admin / admin"
```

---

## 7. Create Airflow admin user (first time only)

```bash
# Exec into the running container to create the user
aws ecs execute-command \
  --cluster ledgerflow-cluster \
  --task $TASK_ARN \
  --container airflow-webserver \
  --interactive \
  --command "airflow users create \
    --username admin \
    --firstname LedgerFlow \
    --lastname Admin \
    --role Admin \
    --email admin@ledgerflow.local \
    --password admin"
```

---

## 8. Force-redeploy after a new ECR push

```bash
aws ecs update-service \
  --cluster ledgerflow-cluster \
  --service ledgerflow-airflow \
  --force-new-deployment
```

---

## Interview talking points

| Question | Answer |
|----------|--------|
| Why ECS Fargate over EC2? | Fargate is serverless containers — no EC2 instances to patch, right-size, or manage. Pay only for container runtime. |
| Why two roles (execution vs task)? | Execution role = what ECS infrastructure can do (pull image, write logs). Task role = what your *code* can do (write to S3, connect to RDS). Least privilege at both levels. |
| Why `assignPublicIp=ENABLED`? | Fargate tasks need a public IP to pull images from ECR (or use NAT gateway). NAT gateway costs ~$32/month — not worth it for a portfolio. |
| Why LocalExecutor not CeleryExecutor? | LocalExecutor runs tasks in subprocesses — simpler, zero extra infrastructure. CeleryExecutor needs Redis + worker fleet, which is overkill until you have 100+ DAGs running concurrently. |
| How do you update the pipeline? | CI pushes new ECR image on merge to main → `aws ecs update-service --force-new-deployment` picks it up automatically. |
