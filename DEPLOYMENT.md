# Deployment Guide

## What changed for cloud deployment

- **Model priority**: default order is now **Groq → Gemini → Qwen** (was Qwen → Groq → Gemini). Groq needs no GPU host, which is the right default once this runs in the cloud rather than on your laptop with Ollama installed. Qwen is still fully supported as a fallback if you run a GPU-backed Ollama host in the same VPC — override with `PRIMARY_LLM=qwen`. Your own BYO API key (Settings page) is still tried before any of this, unchanged.
- **`.env.example`** was carrying the same deprecated-model bugs fixed earlier in the live `.env` — rewritten so a fresh clone doesn't reintroduce them.
- New: `backend/Dockerfile`, `web/Dockerfile` + `nginx.conf.template`, `docker-compose.yml`, `deploy/ecs-task-definition.json`, `deploy/terraform/`, `.github/workflows/deploy.yml`.

## 1. Test locally with Docker first

```bash
cp .env.example .env   # fill in DATABASE_URL, GROQ_API_KEY, GEMINI_API_KEY at minimum
docker compose up --build
```
- Backend: `http://localhost:8000/health`
- Frontend: `http://localhost:8080`

This proves the containers themselves work before anything touches AWS.

## 2. One-time AWS setup

**Secrets Manager** — create these before running Terraform (referenced by ARN, not created by it, since these hold your actual keys):
```bash
aws secretsmanager create-secret --name chatbot/database-url --secret-string "postgresql://..."
aws secretsmanager create-secret --name chatbot/groq-api-key --secret-string "gsk_..."
aws secretsmanager create-secret --name chatbot/gemini-api-key --secret-string "AIza..."
aws secretsmanager create-secret --name chatbot/admin-api-key --secret-string "$(openssl rand -hex 32)"
```

**Terraform** (`deploy/terraform/`) — provisions ECR, ECS cluster/service, ALB, EFS (persistent index storage), IAM roles, CloudWatch. Assumes your VPC and RDS already exist — fill in `terraform.tfvars`:
```hcl
vpc_id                 = "vpc-xxxxxxxx"
private_subnet_ids     = ["subnet-aaa", "subnet-bbb"]
public_subnet_ids      = ["subnet-ccc", "subnet-ddd"]
rds_security_group_id  = "sg-xxxxxxxx"
secret_arns = {
  database_url   = "arn:aws:secretsmanager:...:secret:chatbot/database-url"
  groq_api_key   = "arn:aws:secretsmanager:...:secret:chatbot/groq-api-key"
  gemini_api_key = "arn:aws:secretsmanager:...:secret:chatbot/gemini-api-key"
  admin_api_key  = "arn:aws:secretsmanager:...:secret:chatbot/admin-api-key"
}
```
```bash
cd deploy/terraform
terraform init
terraform validate   # I could not run this myself in this environment — run it before plan/apply
terraform plan
terraform apply
```

⚠️ **I wrote this Terraform carefully but could not execute `terraform validate`/`plan` against a real AWS account from here** (no AWS credentials or `terraform` binary in this environment) — treat it as a strong starting point, not a "definitely works" guarantee. Run `validate` and `plan` yourself and read the plan output before `apply`.

**First image push** (Terraform creates empty ECR repos; push once manually before the ECS service can start):
```bash
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com
docker build -f backend/Dockerfile -t ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/chatbot-backend:latest .
docker push ACCOUNT.dkr.ecr.ap-south-1.amazonaws.com/chatbot-backend:latest
```

## 3. Build the embedding index against the cloud DB

```bash
DATABASE_URL="postgresql://...rds..." python3 -m embeddings.build_index --full
```
Run this once before employees start using it — after that, the automatic 24h scheduler and CI-triggered `/admin/reindex` keep it current (see the earlier explanation of how that works).

## 4. CI/CD

Set these as GitHub repo secrets: `AWS_ROLE_ARN` (OIDC role, no static AWS keys needed), `ECS_CLUSTER`, `ECS_SERVICE`, `ECR_BACKEND_REPO` (all three from `terraform output`), `BACKEND_PUBLIC_URL`, `ADMIN_API_KEY`.

Push to `main` → `.github/workflows/deploy.yml` builds, pushes, deploys to ECS, triggers a reindex, verifies `/health`.

## 5. Frontend hosting

Two options, pick one:
- **S3 + CloudFront** (cheaper, no server to patch) — `cd web && VITE_API_URL=https://your-alb-dns npm run build`, upload `dist/` to S3, serve via CloudFront.
- **The `web/Dockerfile` I built** — runs behind its own ALB/target group in ECS, reverse-proxies `/api` to the backend at container-start time (no rebuild needed if the backend URL changes).

## 6. Before rolling out to "all employees" — one real gap

`org_id` is currently just a plain string the client sends, with no real authentication behind it. For company-wide rollout, put this behind **AWS Cognito or your company SSO** so `org_id` comes from a verified identity token. I'd treat this as a blocker for broad internal launch, not optional polish — flagged here again because it's the one piece I didn't build, on purpose, since it depends on decisions (which SSO provider, what your employee directory looks like) I don't have visibility into.

## What I could verify vs. what I couldn't

| Verified | Not verified (no AWS/Docker/Terraform binary in this environment) |
|---|---|
| Model router change compiles, defaults confirmed correct | Dockerfiles actually build |
| `docker-compose.yml` YAML syntax valid | Terraform `plan`/`apply` succeeds against real AWS |
| ECS task definition JSON syntax valid | ECS service actually reaches steady state |
| GitHub Actions YAML syntax valid | nginx reverse-proxy behavior under real traffic |
| Terraform files: brace-balanced, no gross syntax errors | Full Terraform semantic validation |

Run this through `docker compose up --build` locally first — that's the fastest way to catch anything that needs adjusting before touching real AWS infrastructure.
