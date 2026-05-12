# AWS S3 Data Lake Setup — Step 8b

Run these commands to create the raw data lake bucket.
Replace `<account-id>` and `<region>` with your actual values.

---

## 1. Create the S3 bucket

```bash
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET_NAME="ledgerflow-raw-${ACCOUNT_ID}"
REGION="us-east-1"
echo "Bucket: $BUCKET_NAME"

# Create bucket (us-east-1 does not use LocationConstraint)
aws s3api create-bucket \
  --bucket $BUCKET_NAME \
  --region $REGION

# Block all public access — this data must never be public
aws s3api put-public-access-block \
  --bucket $BUCKET_NAME \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Enable versioning — lets you recover accidentally overwritten files
aws s3api put-bucket-versioning \
  --bucket $BUCKET_NAME \
  --versioning-configuration Status=Enabled

# Enable server-side encryption (AES-256 managed by S3)
aws s3api put-bucket-encryption \
  --bucket $BUCKET_NAME \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

# Add lifecycle rule: move files older than 90 days to Glacier (cost saving)
aws s3api put-bucket-lifecycle-configuration \
  --bucket $BUCKET_NAME \
  --lifecycle-configuration '{
    "Rules": [{
      "ID": "archive-old-raw-files",
      "Status": "Enabled",
      "Filter": {"Prefix": "raw/"},
      "Transitions": [{
        "Days": 90,
        "StorageClass": "GLACIER_IR"
      }]
    }]
  }'

echo "Bucket $BUCKET_NAME created and configured."
```

---

## 2. Set bucket name in GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets → Actions):

```
S3_BUCKET = ledgerflow-raw-<account-id>
USE_S3    = true
```

---

## 3. S3 folder structure

After `load_bronze.py` runs with `USE_S3=true`, files land here:

```
s3://ledgerflow-raw-<account-id>/
└── raw/
    ├── transactions/
    │   └── 2026/05/17/
    │       └── transactions.csv
    ├── customers/
    │   └── 2026/05/17/
    │       └── customers.csv
    ├── accounts/
    │   └── 2026/05/17/
    │       └── accounts.csv
    └── loans/
        └── 2026/05/17/
            └── loans.csv
```

Date-partitioned paths allow:
- Point-in-time recovery ("what did Tuesday's load look like?")
- Athena/Glue partitioned queries without full-scan
- Lifecycle policies that archive by age

---

## 4. Enable S3 upload in the pipeline

```bash
# Set in your shell or in AWS Secrets Manager
export USE_S3=true
export S3_BUCKET=ledgerflow-raw-<account-id>
export AWS_REGION=us-east-1

# Now load_bronze.py will archive each CSV to S3 before loading to RDS
python ingestion/load_bronze.py
```

---

## Interview talking points

| Question | Answer |
|----------|--------|
| Why S3 as a data lake? | S3 is $0.023/GB/month — cheap enough to keep every raw file forever. If RDS is corrupted you re-load from S3. |
| Why versioning? | Accidental overwrite of a large CSV doesn't lose data — previous version still exists. |
| Why Glacier transition at 90 days? | Raw files older than 90 days are rarely accessed. Glacier IR costs $0.004/GB vs $0.023/GB — ~6x cheaper. |
| Why AES-256 not KMS? | AES-256 (SSE-S3) is free. KMS adds $0.03 per 10K requests — fine for prod with compliance requirements, overkill for a portfolio. |
| Why date partitioning? | AWS Athena charges per byte scanned. Partition pruning (`WHERE date='2026-05-17'`) avoids scanning the whole bucket. |
