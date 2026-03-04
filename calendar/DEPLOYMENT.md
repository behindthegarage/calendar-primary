# Calendar Dashboard VPS Deployment

## Artifacts created

- App: `calendar/dashboard.py` (host/port constants + structured logging)
- Systemd unit: `/home/openclaw/calendar-dashboard.service`
- Nginx path snippet: `calendar/nginx-calendar-primary-location.conf`
- Optional nginx subdomain server block: `calendar/nginx-calendar.hariclaw.com.conf`
- Deploy script: `calendar/deploy-dashboard.sh`

## Default deployment target

- VPS: `openclaw@162.212.153.134`
- App dir on VPS: `/home/openclaw/calendar/`
- Service name: `calendar-dashboard.service`
- Public URL (default mode): `https://hariclaw.com/calendar-primary/`

## Run deploy

```bash
cd /home/openclaw/.openclaw/workspace/calendar
./deploy-dashboard.sh
```

## Optional subdomain mode

```bash
./deploy-dashboard.sh --mode subdomain --certbot-email you@example.com
```

This installs `calendar.hariclaw.com` nginx config and requests SSL via certbot.
