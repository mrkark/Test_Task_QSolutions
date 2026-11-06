#!/bin/sh
set -e

mkdir -p /app/uploads
chown -R www-data:www-data /app/uploads || true
chmod -R 777 /app/uploads || true

exec "$@"
