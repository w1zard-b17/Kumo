#!/bin/ksh
#
# Install the Kumo storage agent on the OpenBSD host.   usage: doas ./install.sh
#
set -e
cd "$(dirname "$0")"

[ "$(id -u)" = 0 ] || { echo "install.sh: run as root (doas ./install.sh)"; exit 1; }

LIB=/usr/local/lib/kumo-agent

command -v python3 >/dev/null 2>&1 || pkg_add -I python%3

if ! id _kumo >/dev/null 2>&1; then
	useradd -g =uid -c "Kumo storage agent" -d /var/empty -s /sbin/nologin _kumo
fi

install -d -m 755 $LIB /etc/kumo
rm -rf $LIB/kumo_agent
cp -R kumo_agent $LIB/
find $LIB -name __pycache__ -prune -exec rm -rf {} +
chown -R root:wheel $LIB
chmod -R a+rX,go-w $LIB

install -m 755 bin/kumo-agent bin/kumoctl /usr/local/bin/
install -m 555 etc/rc.d/kumo_agent /etc/rc.d/kumo_agent

if [ ! -f /etc/kumo/agent.conf ]; then
	install -m 640 -o root -g _kumo etc/agent.conf.sample /etc/kumo/agent.conf
	echo "wrote /etc/kumo/agent.conf; check 'bind' against: ifconfig tap0"
fi

install -d -m 700 -o _kumo -g _kumo /var/db/kumo
kumoctl init
rcctl enable kumo_agent

cat <<'EOF'

Kumo agent installed. Next:

  1. Add the HDD to /etc/fstab by DUID (see: kumoctl disk scan), e.g.
       3eb7f9da875cb9ee.a /srv/kumo/hdd0 ffs rw,nodev,nosuid,noexec 1 2
     then: mkdir -p /srv/kumo/hdd0 && mount /srv/kumo/hdd0

  2. kumoctl disk add hdd0 /srv/kumo/hdd0 --device 3eb7f9da875cb9ee
  3. kumoctl vm add film --disk hdd0 --ip 100.64.1.3 --root library
       -> copy the printed token to the VM
  4. merge etc/pf.conf.kumo into /etc/pf.conf, pfctl -f /etc/pf.conf
  5. rcctl start kumo_agent
EOF
