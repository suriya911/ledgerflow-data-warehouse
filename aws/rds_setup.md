# AWS RDS PostgreSQL Setup — Step 8a

Run these commands once to create the managed PostgreSQL database.
Replace `<account-id>`, `<region>`, `<your-password>` with real values.

---

## Prerequisites

```bash
# Install and configure AWS CLI
pip install awscli
aws configure
# Enter: AWS Access Key ID, Secret Access Key, region (us-east-1), output (json)

# Verify identity
aws sts get-caller-identity
```

---

## 1. Create a security group for RDS

```bash
# Get your default VPC ID
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" \
  --output text)
echo "VPC: $VPC_ID"

# Create security group — only ECS tasks can reach port 5432
aws ec2 create-security-group \
  --group-name ledgerflow-rds-sg \
  --description "LedgerFlow RDS — inbound 5432 from ECS only" \
  --vpc-id $VPC_ID

# Save the security group ID
RDS_SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=ledgerflow-rds-sg" \
  --query "SecurityGroups[0].GroupId" \
  --output text)
echo "RDS SG: $RDS_SG_ID"

# Allow port 5432 from within the VPC (ECS tasks run in the same VPC)
VPC_CIDR=$(aws ec2 describe-vpcs \
  --vpc-ids $VPC_ID \
  --query "Vpcs[0].CidrBlock" \
  --output text)

aws ec2 authorize-security-group-ingress \
  --group-id $RDS_SG_ID \
  --protocol tcp \
  --port 5432 \
  --cidr $VPC_CIDR
```

---

## 2. Create the RDS instance

```bash
# Get two subnet IDs from different AZs (required for subnet group)
SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query "Subnets[0:2].SubnetId" \
  --output text | tr '\t' ',')
echo "Subnets: $SUBNET_IDS"

# Create DB subnet group
aws rds create-db-subnet-group \
  --db-subnet-group-name ledgerflow-subnet-group \
  --db-subnet-group-description "LedgerFlow RDS subnet group" \
  --subnet-ids $(echo $SUBNET_IDS | tr ',' ' ')

# Create RDS instance (db.t3.micro = ~$13/month)
# Multi-AZ=false to keep costs down for a portfolio project
aws rds create-db-instance \
  --db-instance-identifier ledgerflow-db \
  --db-instance-class db.t3.micro \
  --engine postgres \
  --engine-version 15.4 \
  --master-username ledger \
  --master-user-password <your-password> \
  --db-name ledgerflow \
  --allocated-storage 20 \
  --storage-type gp3 \
  --no-multi-az \
  --no-publicly-accessible \
  --vpc-security-group-ids $RDS_SG_ID \
  --db-subnet-group-name ledgerflow-subnet-group \
  --backup-retention-period 7 \
  --deletion-protection \
  --tags Key=Project,Value=LedgerFlow

echo "RDS creation started — takes ~5 minutes to become available"
```

---

## 3. Wait for RDS to be available

```bash
aws rds wait db-instance-available \
  --db-instance-identifier ledgerflow-db

# Get the endpoint
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier ledgerflow-db \
  --query "DBInstances[0].Endpoint.Address" \
  --output text)
echo "RDS endpoint: $RDS_ENDPOINT"
```

---

## 4. Store credentials in AWS Secrets Manager

```bash
# Store connection string as a secret — ECS task and Vercel read from here
aws secretsmanager create-secret \
  --name ledgerflow/db \
  --description "LedgerFlow PostgreSQL connection string" \
  --secret-string "{
    \"host\": \"$RDS_ENDPOINT\",
    \"port\": \"5432\",
    \"dbname\": \"ledgerflow\",
    \"username\": \"ledger\",
    \"password\": \"<your-password>\",
    \"DATABASE_URL\": \"postgresql://ledger:<your-password>@$RDS_ENDPOINT:5432/ledgerflow\"
  }"

echo "Secret stored at: ledgerflow/db"
```

---

## 5. Create database schemas

```bash
# Connect via psql (requires network access — run from a bastion or local with VPN)
# Or use AWS RDS Query Editor in the console

PGPASSWORD=<your-password> psql \
  -h $RDS_ENDPOINT \
  -U ledger \
  -d ledgerflow \
  -c "
    CREATE SCHEMA IF NOT EXISTS bronze;
    CREATE SCHEMA IF NOT EXISTS main_silver;
    CREATE SCHEMA IF NOT EXISTS main_gold;
    GRANT ALL ON SCHEMA bronze, main_silver, main_gold TO ledger;
  "
```

---

## Interview talking points

| Question | Answer |
|----------|--------|
| Why `db.t3.micro`? | Cheapest RDS tier (~$13/mo) — fine for a portfolio project. Scale to `db.r6g.large` in prod. |
| Why `no-multi-az`? | Multi-AZ doubles the cost. Enable it in prod for <30s failover. |
| Why `no-publicly-accessible`? | RDS should never be exposed to the internet. ECS tasks connect via VPC private networking. |
| Why Secrets Manager over env vars? | Secrets Manager rotates credentials, logs every access, and never exposes values in container logs. |
| Why `gp3` storage? | gp3 provides 3,000 IOPS baseline for free — better than gp2 at the same cost. |
| Why `deletion-protection`? | Prevents accidental `terraform destroy` or console misclick from dropping production data. |
