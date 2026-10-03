#!/bin/sh
# Keep yt-dlp current. Most failures after a YouTube change are fixed upstream.
# Installed as /opt/kumo/update-ytdlp.sh and run weekly from /etc/periodic/weekly/kumo-ytdlp.
set -eu

before=$(/opt/kumo/venv/bin/python -c 'from yt_dlp.version import __version__; print(__version__)' 2>/dev/null || echo none)
/opt/kumo/venv/bin/pip install --quiet --no-cache-dir --upgrade yt-dlp
after=$(/opt/kumo/venv/bin/python -c 'from yt_dlp.version import __version__; print(__version__)')

if [ "$before" != "$after" ]; then
	echo "yt-dlp $before -> $after"
	# restart only when the queue is idle, otherwise the next run picks it up
	busy=$(sqlite3 /var/lib/kumo/kumo.db "SELECT COUNT(*) FROM jobs WHERE status IN ('downloading','converting','uploading')" 2>/dev/null || echo 0)
	if [ "$busy" = "0" ]; then
		rc-service kumo restart
	else
		echo "downloads running; restart kumo later to load the new yt-dlp"
	fi
else
	echo "yt-dlp $after is current"
fi
