#!/bin/bash
set -e
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/root/forge-fx/backups/$TS
mkdir -p "$BACKUP_DIR"
APP_IP=$(docker inspect forge-fx-app-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
echo "Backing up to $BACKUP_DIR (app $APP_IP)"
cp /var/lib/docker/volumes/forge-fx_forge-data/_data/forge.db "$BACKUP_DIR/forge.db"
curl -sS "http://${APP_IP}:8000/api/health" > "$BACKUP_DIR/health.json"
curl -sS "http://${APP_IP}:8000/api/status" > "$BACKUP_DIR/status.json"
curl -sS "http://${APP_IP}:8000/api/portfolio" > "$BACKUP_DIR/portfolio.json"
curl -sS "http://${APP_IP}:8000/api/engines/status" > "$BACKUP_DIR/engines.json"
curl -sS "http://${APP_IP}:8000/api/cycles?limit=25" > "$BACKUP_DIR/cycles_recent.json"
ls -lh "$BACKUP_DIR"
echo "--- stopping forge-fx-app-1 ---"
docker stop forge-fx-app-1
docker ps -a --filter name=forge-fx --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -tlnp | grep ':8000' || echo 'host port 8000: not listening (expected)'
echo "BACKUP_DIR=$BACKUP_DIR"
