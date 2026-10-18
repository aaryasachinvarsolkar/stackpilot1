# STACKPILOT — Deployment Guide

STACKPILOT is architected for containerized deployment via Docker Compose, as well as cloud-native deployment on Kubernetes, AWS ECS, GCP Cloud Run, or standard Linux VMs.

---

## 1. Quick Deployment via Docker Compose

### Prerequisites
- Docker Engine 24.0+
- Docker Compose v2.20+

### Production Launch
```bash
# 1. Configure environment variables
cp .env.example .env
# Edit .env with production credentials (DATABASE_URL, JWT_SECRET, LLM_API_KEY)

# 2. Build and launch services
docker compose -f docker-compose.yml up -d --build

# 3. Check logs
docker compose logs -f backend
```

---

## 2. Cloud Architecture (AWS / GCP / Azure)

```
[Cloudflare / AWS CloudFront CDN]
              │
              ▼
   [Application Load Balancer]
       │                 │
       ▼                 ▼
[Frontend Service]  [Backend API Service (FastAPI)]
 (Next.js Cluster)         │
                           ├─► [AWS RDS Aurora PostgreSQL + pgvector]
                           ├─► [AWS ElastiCache Redis]
                           └─► [Docker / MicroVM Sandbox Cluster]
```

---

## 3. Database Migration & Initialization
When running against PostgreSQL with `pgvector`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
FastAPI backend automatically registers schemas and manages index creation.
