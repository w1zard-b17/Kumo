# Kumo

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Svelte](https://img.shields.io/badge/Svelte-5-FF3E00?style=flat-square&logo=svelte&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-WAL-003B57?style=flat-square&logo=sqlite&logoColor=white)
![nginx](https://img.shields.io/badge/nginx-009639?style=flat-square&logo=nginx&logoColor=white)
![FFmpeg](https://img.shields.io/badge/FFmpeg-007808?style=flat-square&logo=ffmpeg&logoColor=white)
![Alpine Linux](https://img.shields.io/badge/Alpine_Linux-0D597F?style=flat-square&logo=alpinelinux&logoColor=white)
![OpenBSD](https://img.shields.io/badge/OpenBSD-F2CA30?style=flat-square&logo=openbsd&logoColor=black)

Self-hosted streaming app for a personal documentary library.

Paste a YouTube link, pick the quality and classify it, and Kumo downloads the video as MP4, files it under its category on a hard-drive bay, and streams it to any browser on the LAN with resume, subtitles and chapter markers.

The system is split across two machines. An Alpine VM with 1 GB of RAM runs the web app, the API and the download queue. A storage agent on the OpenBSD host owns the disks: the VM never mounts the bay, it authenticates with a bearer token and requests media by file ID.

```
LAN browser ──:8096──▶ OpenBSD host (pf rdr) ──▶ Alpine VM
                                                 ├─ nginx      static SPA, /api proxy, media streaming
                                                 ├─ uvicorn    FastAPI + download worker (yt-dlp, ffmpeg)
                                                 └─ SQLite     library, queue, playback state
                                                        │ bearer token, tap interface only
                                                        ▼
                                       kumo-agent on the host ──▶ /library/<Category>/…
```

## Features

- Link validation and metadata preview for videos and playlists
- Guided flow: download options, required classification, metadata, confirmation
- Download queue with progress, pause, resume, retry and cancel
- Library with grid, list and grouped views, filters, search and bulk actions
- Player with resume position, speed, subtitles, chapters and next-up
- Collections, categories, tags and a settings page for storage and defaults

## Design notes

Three constraints shaped the implementation.

**1 GB of RAM on the VM.** Video bytes never pass through Python. The API authorises a request and replies with an `X-Accel-Redirect`; nginx then streams the file from the storage agent with HTTP Range support, so seeking works and memory use stays flat.

**The host owns the disks.** The agent is the only process that touches the bay. It addresses files by opaque ID, verifies per-VM tokens and source IPs, enforces quotas and a free-space reserve, writes uploads through a temporary file to avoid overwrites, and refuses all I/O when nothing is mounted, so a powered-off bay cannot fill the root filesystem.

**Downloads fail often.** Private, age-restricted, geo-blocked and live videos are detected and reported in plain language. Network errors are retried with exponential backoff. Jobs can be paused or cancelled mid-transfer without leaving partial files on either machine.

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | Svelte 5, Vite, Tailwind CSS 4 |
| API | Python 3, FastAPI, uvicorn |
| Database | SQLite in WAL mode |
| Media | yt-dlp, ffmpeg |
| Storage agent | Python standard library only, no dependencies |
| Serving | nginx with `X-Accel-Redirect`, Range support and a proxy cache |
| Platforms | Alpine Linux (OpenRC), OpenBSD (rc.d, pf, vmd) |

## Installation

### 1. OpenBSD host

```sh
doas sh host/install.sh
kumoctl disk scan                     # list kernel disks and their DUIDs
```

Add the bay to `/etc/fstab` by DUID, mount it, then register the disk and the VM:

```sh
kumoctl disk add hdd0 /srv/kumo/hdd0 --device <duid>
kumoctl vm add film --disk hdd0 --ip 100.64.1.3 --root library
```

The command prints a token once. Merge `host/etc/pf.conf.kumo` into `/etc/pf.conf`, reload pf, then `rcctl start kumo_agent`.

### 2. Alpine VM

Copy the `vm` directory to the VM and run, as root:

```sh
KUMO_AGENT_TOKEN=<token from step 1> sh deploy/install.sh
```

This installs the packages, a virtualenv, the nginx site on port 8096 and the OpenRC service. The app is then reachable at `http://<host-ip>:8096`.

To change the token later, edit `/etc/kumo/kumo.env` and run `kumo-setup-token`.

### 3. Development

```sh
# storage agent against a local folder
cd host && mkdir -p devdisk
printf '[agent]\nbind=127.0.0.1\nport=9090\ndb=./dev.db\nrequire_mount=no\n' > dev.conf
python -m kumo_agent.cli -c dev.conf disk add dev ./devdisk
python -m kumo_agent.cli -c dev.conf vm add dev --disk dev --ip 127.0.0.1
python -m kumo_agent -c dev.conf -v

# API (KUMO_ACCEL=0 makes FastAPI relay media itself, since nginx is absent)
cd vm/api && pip install -r requirements.txt
KUMO_DATA=./.data KUMO_AGENT_URL=http://127.0.0.1:9090 KUMO_AGENT_TOKEN=<token> \
  KUMO_ACCEL=0 uvicorn kumo.main:app --port 8000

# frontend with hot reload, proxying /api to port 8000
cd vm/web && npm install && npm run dev
```

API documentation is served at `/api/docs`.

## Layout

```
host/                OpenBSD storage agent
  kumo_agent/        HTTP API, SQLite store, disk handling, kumoctl
  etc/               agent config, rc.d service, pf rules
vm/
  api/kumo/          FastAPI app, download worker, yt-dlp and agent clients
  web/               Svelte frontend
  deploy/            nginx site, OpenRC service, install scripts
```
