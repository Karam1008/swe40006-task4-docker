# SWE40006 Deployment Portfolio Task 4 - Docker

Container application deployment and orchestration, built progressively across
four grade levels. Every image is published to Docker Hub and runs unchanged on
two hosts: Docker Desktop (Windows 11, WSL 2) and an AWS EC2 Amazon Linux 2023 host.

| Level | Folder | What it is | Image |
|---|---|---|---|
| 4.1 Pass | - | Docker Desktop install + `hello-world` | `hello-world` |
| 4.2 Credit | `task4.2-flask-basic/` | Basic Flask JSON app on a designated port | `karamjot1008/swe40006-flask-basic` |
| 4.3 Distinction | `task4.3-docknotes/` | DockNotes: FastAPI + Redis + Caddy, optimised multi-stage build, isolated networks | `karamjot1008/swe40006-docknotes` |
| 4.4 High Distinction | `task4.4-logalyzer/` | logalyzer: non-web access-log analysis CLI with volumes, tests and graceful lifecycle | `karamjot1008/swe40006-logalyzer` |

```

├── task4.2-flask-basic/     app.py, requirements.txt, Dockerfile
├── task4.3-docknotes/       app/, Dockerfile, Dockerfile.naive, compose.yaml, Caddyfile, .env.example
├── task4.4-logalyzer/       logalyzer/, tests/, Dockerfile, compose.yaml, data/
├── scripts/                 ec2-docker-host-userdata.sh (secondary Docker host bootstrap)
└── docs/RUNBOOK.md          step-by-step execution guide with screenshot checkpoints
```

## Quick start

```powershell
# 4.2
docker build -t swe40006-flask-basic:1.0.0 task4.2-flask-basic
docker run -d --name flask-basic -p 8080:5000 swe40006-flask-basic:1.0.0

# 4.3  (copy .env.example to .env and set DOCKERHUB_USER first)
cd task4.3-docknotes; docker compose up -d --build

# 4.4
cd task4.4-logalyzer
docker build -t logalyzer:1.0.0 .
docker run --rm logalyzer:1.0.0 --help

