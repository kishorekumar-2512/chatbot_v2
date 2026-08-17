# Blue-Green Deployment & Cloud Migration Guide

This guide details the production architecture, cloud database migration steps, automated CI/CD pipeline, and manual zero-downtime cutover/rollback procedures for **chatbot_v2**.

---

## 1. Production Architecture Overview

The system uses a containerized **Blue-Green Deployment Topology** on a single cloud VM (AWS EC2 / DigitalOcean Droplet / GCP Compute Engine) fronted by a reverse-proxy (Nginx):

```
                        Public Traffic (:80 / :443)
                                     │
                                     ▼
                   ┌───────────────────────────────────┐
                   │  Nginx Reverse Proxy / Load Balancer│
                   │   (/etc/nginx/conf.d/upstream.conf) │
                   └─────────────────┬─────────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 │ (Active Upstream)                     │ (Idle / Staging)
                 ▼                                       ▼
       ┌───────────────────┐                   ┌───────────────────┐
       │   BLUE STACK      │                   │   GREEN STACK     │
       │ web-blue    :8081 │                   │ web-green   :8082 │
       │ backend-blue:8001 │                   │ backend-green:8002│
       └─────────┬─────────┘                   └─────────┬─────────┘
                 │                                       │
                 └───────────────────┬───────────────────┘
                                     │
                                     ▼
                     ┌───────────────────────────────┐
                     │     SHARED STATE LAYER        │
                     │  • Managed Cloud PostgreSQL   │
                     │  • Shared ChromaDB Volume     │
                     │  • Shared Key Store Volume    │
                     │  • Shared Feedback/Reports    │
                     └───────────────────────────────┘
```

### Key Principles:
1. **Stateless App Doubling**: Only the application services (`web` and `backend`) exist in Blue and Green duplicates.
2. **Shared Cloud State**: Both Blue and Green connect to the **same** single managed cloud database and shared Docker volumes (`chroma_data`, `key_store_data`, `feedback_data`, `reports_data`).
3. **Atomic Cutover**: Upstream targets are swapped in Nginx followed by `nginx -s reload` (sub-millisecond, zero dropped connections).
4. **Instant Rollback**: If an issue arises post-cutover, rolling back is an instantaneous reverse traffic switch—no rebuilding or container restarts required.

---

## 2. Cloud Database Migration (pgAdmin/Local Postgres → Cloud DB)

To migrate the local database (`intern_db`) to a managed cloud database instance (AWS RDS, Supabase, DigitalOcean Managed PostgreSQL):

### Step 2.1: Export Local PostgreSQL Schema & Data
From your terminal or pgAdmin:
```bash
# Dump the local database to SQL file
pg_dump -U postgres -h localhost -p 5432 -d intern_db -F c -b -v -f intern_db_backup.dump

# Or export as plain SQL script:
pg_dump -U postgres -h localhost -p 5432 -d intern_db --clean --if-exists -f intern_db_dump.sql
```

### Step 2.2: Import into Managed Cloud Database
```bash
# Restore custom-format dump to RDS / Cloud DB:
pg_restore -U <cloud_user> -h <cloud_db_host> -p 5432 -d <cloud_dbname> -v intern_db_backup.dump

# Or run plain SQL import:
psql -U <cloud_user> -h <cloud_db_host> -p 5432 -d <cloud_dbname> -f intern_db_dump.sql
```

### Step 2.3: Configure Cloud Connection in `.env.blue` and `.env.green`
Set the cloud connection string with SSL:
```env
DATABASE_URL=postgresql://<user>:<password>@<cloud_db_host>:5432/<dbname>?sslmode=require
```

### Step 2.4: Build Semantic Embedding Index Against Cloud DB
Run the one-time indexing against the cloud DB:
```bash
DATABASE_URL="postgresql://<user>:<pass>@<cloud_db_host>:5432/<dbname>?sslmode=require" python -m embeddings.build_index --full
```

---

## 3. Server Setup & One-Time Configuration

### Step 3.1: Server Directory & Permissions
On the target production VM (`/opt/chatbot_v2`):
```bash
git clone https://github.com/kishorekumar-2512/chatbot_v2.git /opt/chatbot_v2
cd /opt/chatbot_v2
chmod +x scripts/*.sh
```

### Step 3.2: Configure Environment Files
Copy and edit the production environment files:
```bash
cp .env.production.example .env.blue
cp .env.production.example .env.green
# Edit .env.blue and .env.green with your production API keys and DATABASE_URL
```

### Step 3.3: Set Up Host Nginx Reverse Proxy
Install Nginx on the host VM:
```bash
sudo apt-get update && sudo apt-get install -y nginx

# Copy upstream and site configs
sudo cp nginx/upstream_blue.conf /etc/nginx/conf.d/upstream_active.conf
sudo cp nginx/nginx.conf /etc/nginx/sites-available/chatbot.conf
sudo ln -s /etc/nginx/sites-available/chatbot.conf /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

sudo nginx -t
sudo systemctl restart nginx
echo "blue" > /opt/chatbot_v2/.active_color
```

### Step 3.4: Initial Blue Stack Launch
```bash
docker compose -f docker-compose.blue.yml up -d --build
./scripts/health_check.sh blue
```

---

## 4. Manual Deployment & Cutover Workflow

When deploying updates manually:

### 1. Check Currently Live Color
```bash
cat .active_color
# Example output: blue
```

### 2. Build & Deploy New Release to the Idle Color (e.g., Green)
```bash
docker compose -f docker-compose.green.yml build
docker compose -f docker-compose.green.yml up -d
```

### 3. Run Automated Smoke Tests against Idle Stack
```bash
./scripts/health_check.sh green
```

### 4. Perform Atomic Cutover
```bash
./scripts/switch_traffic.sh green
```
Traffic is now routed to Green instantly. The Blue stack remains running in the background as the warm standby.

---

## 5. Instant Rollback Procedure

If a bug is discovered on the active stack, execute rollback with **zero downtime**:

```bash
# To roll back immediately to Blue:
./scripts/switch_traffic.sh blue

# Or if Green was the previous stable version:
./scripts/switch_traffic.sh green
```

Nginx reloads in under 1 millisecond. No container rebuilding or restarting is needed.

---

## 6. Automated CI/CD (GitHub Actions)

The `.github/workflows/deploy.yml` pipeline automatically performs the entire blue-green lifecycle on every push to `main`:

1. **Build & Package**: Builds multi-stage Docker images for `backend` and `web` and pushes them to GitHub Container Registry (`ghcr.io`).
2. **Detect Active / Idle Color**: Queries `.active_color` on the production server.
3. **Pull & Deploy to Idle**: Deploys the new image tag to the idle stack (`docker-compose.<idle>.yml up -d`).
4. **Automated Health Checks**: Runs `scripts/health_check.sh` on the internal idle port.
5. **Atomic Traffic Cutover**: Runs `scripts/switch_traffic.sh` on success. If health checks fail, the workflow aborts and traffic remains safely on the active stack.

### Required GitHub Secrets:
- `DEPLOY_HOST`: Public IP / domain of production VM
- `DEPLOY_USER`: SSH username (e.g. `ubuntu`)
- `DEPLOY_SSH_KEY`: SSH private key for deployment access

---

## 7. Operational Troubleshooting

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| **Nginx returns 502 Bad Gateway** | Target container is not running or healthcheck failed | Check `docker ps` and run `./scripts/health_check.sh <color>` |
| **CORS error on chat queries** | `FRONTEND_ORIGIN` missing target port | Verify `FRONTEND_ORIGIN` in `.env.<color>` includes public domain & local port |
| **Vector search fails** | `chroma_data` volume not mounted | Verify named volume `chatbot_shared_chroma_data` is mounted in compose file |
| **BYO API keys not persisting** | `key_store_data` volume not shared | Ensure `chatbot_shared_key_store_data` is defined under `volumes` |
