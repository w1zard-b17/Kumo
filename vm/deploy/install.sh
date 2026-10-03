#!/bin/sh
#
# Install or upgrade Kumo-Film on the Alpine VM.
#
# Run as root from the vm/ directory:  ./deploy/install.sh
# Optionally pass the storage token:   KUMO_AGENT_TOKEN=kumo_... ./deploy/install.sh
#
set -eu
cd "$(dirname "$0")/.."

[ "$(id -u)" = 0 ] || { echo "install.sh: run as root"; exit 1; }

echo "==> packages"
apk add --no-cache python3 py3-pip ffmpeg nginx sqlite curl ca-certificates

echo "==> user"
getent group kumo >/dev/null || addgroup -S kumo
getent passwd kumo >/dev/null || adduser -S -D -H -h /var/lib/kumo -s /sbin/nologin -G kumo -g "Kumo-Film" kumo

install -d -m 0755 /opt/kumo /opt/kumo/web
install -d -m 0750 -o kumo -g kumo /var/lib/kumo /var/lib/kumo/tmp /var/log/kumo
install -d -m 0750 -o root -g kumo /etc/kumo
install -d -m 0750 -o nginx -g nginx /var/cache/nginx/kumo

echo "==> python venv"
[ -x /opt/kumo/venv/bin/python ] || python3 -m venv /opt/kumo/venv
/opt/kumo/venv/bin/pip install --quiet --no-cache-dir --upgrade pip
/opt/kumo/venv/bin/pip install --quiet --no-cache-dir -r api/requirements.txt

echo "==> api"
rm -rf /opt/kumo/api.new
cp -R api /opt/kumo/api.new
find /opt/kumo/api.new -name __pycache__ -prune -exec rm -rf {} +
rm -rf /opt/kumo/api
mv /opt/kumo/api.new /opt/kumo/api

echo "==> web"
if [ ! -f web/dist/index.html ]; then
	echo "    web/dist missing, building (temporary nodejs, ~250 MB RAM)"
	apk add --no-cache --virtual .kumo-build nodejs npm
	(cd web && npm ci --no-audit --no-fund && npm run build)
	apk del .kumo-build
fi
rm -rf /opt/kumo/web/*
cp -R web/dist/. /opt/kumo/web/
chmod -R a+rX /opt/kumo/web

echo "==> config"
if [ ! -f /etc/kumo/kumo.env ]; then
	secret=$(head -c 32 /dev/urandom | base64 | tr -d '/+=\n' | cut -c1-43)
	sed -e "s|^KUMO_SECRET=.*|KUMO_SECRET=$secret|" \
	    -e "s|^KUMO_AGENT_TOKEN=.*|KUMO_AGENT_TOKEN=${KUMO_AGENT_TOKEN:-}|" \
	    deploy/kumo.env.sample > /etc/kumo/kumo.env
	chown root:kumo /etc/kumo/kumo.env
	chmod 0640 /etc/kumo/kumo.env
	echo "    wrote /etc/kumo/kumo.env"
fi

install -m 0755 deploy/kumo-setup-token /usr/local/bin/kumo-setup-token
install -m 0755 deploy/update-ytdlp.sh /opt/kumo/update-ytdlp.sh
ln -sf /opt/kumo/update-ytdlp.sh /etc/periodic/weekly/kumo-ytdlp
install -m 0755 deploy/openrc/kumo /etc/init.d/kumo

install -d -m 0750 -o root -g nginx /etc/nginx/kumo
[ -f /etc/nginx/kumo/agent-upstream.conf ] || echo "server 100.64.1.2:9090;" > /etc/nginx/kumo/agent-upstream.conf
[ -f /etc/nginx/kumo/agent-auth.conf ] || echo 'proxy_set_header Authorization "Bearer unset";' > /etc/nginx/kumo/agent-auth.conf
chown root:nginx /etc/nginx/kumo/*.conf
chmod 0640 /etc/nginx/kumo/*.conf
install -m 0644 deploy/nginx/kumo.conf /etc/nginx/http.d/kumo.conf
# Alpine's stock default server answers 404 on :80; Kumo only needs :8096
rm -f /etc/nginx/http.d/default.conf

rc-update add kumo default >/dev/null
rc-update add nginx default >/dev/null
rc-update add crond default >/dev/null 2>&1 || true

echo "==> start"
if grep -q '^KUMO_AGENT_TOKEN=.\+' /etc/kumo/kumo.env; then
	kumo-setup-token
else
	nginx -t && (rc-service nginx reload 2>/dev/null || rc-service nginx start)
	rc-service kumo restart
	cat <<'EOF'

Kumo is running on :8096 but has no storage token yet. On the OpenBSD host:
    kumoctl vm add film --disk hdd0 --ip <this VM's 100.64.x.3> --root library
Put the printed token in /etc/kumo/kumo.env (KUMO_AGENT_TOKEN=...) and run: kumo-setup-token
EOF
fi

echo
echo "Kumo-Film is up:  http://<host LAN IP>:8096"
