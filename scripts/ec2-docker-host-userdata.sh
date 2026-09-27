#!/bin/bash
# SWE40006 Task 4 - secondary Docker host bootstrap for Amazon Linux 2023.
# Paste into EC2 "User data" at launch. Runs once, as root, on first boot.
# Output is written to /var/log/cloud-init-output.log
set -euxo pipefail

dnf update -y
dnf install -y docker git

systemctl enable --now docker
usermod -aG docker ec2-user

# The Docker Compose v2 plugin is not packaged for Amazon Linux 2023,
# so the official release binary for this CPU architecture is installed.
ARCH="$(uname -m)"   # x86_64 on t3.micro, aarch64 on t4g
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-${ARCH}" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

docker version
docker compose version
echo "SWE40006 Docker host bootstrap complete"
