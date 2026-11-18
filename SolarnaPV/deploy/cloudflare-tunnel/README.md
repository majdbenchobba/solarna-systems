# Solarna production tunnel

Use this profile on a dedicated Linux host with Docker Compose. The profile does
not publish ports 80, 443, or 8080.

## Cloudflare

Create a dedicated named tunnel and public hostname:

- Hostname: `pv.solarnasystems.com`
- Service: `http://127.0.0.1:8765`

Keep the existing apex, `www`, LeadForge, mail, and project routes unchanged.
Save the tunnel token as a single line in
`secrets/cloudflare-tunnel-token`. Do not commit this file.

The application and connector share one private container network namespace, so
the existing loopback tunnel route works without publishing an application
port.

## Start

Copy `.env.tunnel.example` to `.env.tunnel`, enter the Supabase project URL and
publishable key, and verify the domain.

```bash
mkdir -p secrets
chmod 700 secrets
sudo chown 65532:65532 secrets/cloudflare-tunnel-token
sudo chmod 400 secrets/cloudflare-tunnel-token
docker compose --env-file .env.tunnel -f compose.tunnel.yaml config
docker compose --env-file .env.tunnel -f compose.tunnel.yaml up --build -d
docker compose --env-file .env.tunnel -f compose.tunnel.yaml ps
```

Verify:

```bash
curl --fail https://pv.solarnasystems.com/api/health
curl --fail --output /dev/null \
  https://pv.solarnasystems.com/downloads/solarna-android.apk
curl --fail --output /dev/null \
  https://pv.solarnasystems.com/downloads/solarna-ios-project.zip
```

## Update

Replace the release files, then run:

```bash
docker compose --env-file .env.tunnel -f compose.tunnel.yaml \
  up --build -d --remove-orphans
```

## Stop

```bash
docker compose --env-file .env.tunnel -f compose.tunnel.yaml down
```

Persistent weather and report data remain in the named Docker volumes.

## Current Windows host

The repository includes `scripts/production/start-solarna-production.ps1` for the present
Windows deployment. It starts the Python server on `127.0.0.1:8765` and the named
tunnel without exposing a local network port.

The launcher reads:

- `secrets/supabase-url.txt`
- `secrets/supabase-publishable-key.txt`
- `secrets/authorized-emails.txt`
- `secrets/cloudflared-token.txt`

Run `scripts/production/setup-solarna-production.ps1` to save the Supabase configuration and copy
the named-tunnel token into the ignored, restricted directory. The files are
excluded from release packages.
