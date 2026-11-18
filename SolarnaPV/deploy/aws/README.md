# AWS production deployment

Solarna runs on an AWS Lightsail Ubuntu instance in Frankfurt. Docker Compose
starts the application and a connector for the existing named Cloudflare
tunnel, so no public application ports or DNS changes are required.

Recommended bundle:

- `small_3_0`
- 2 vCPU
- 2 GB RAM
- 60 GB SSD

Only SSH from the deployment address is allowed by the Lightsail firewall. The
application remains private behind the Cloudflare tunnel.

## Deploy

Extract `Solarna-server.zip` into `/opt/solarna`, create `.env.tunnel`, and save
the existing named-tunnel token at
`/opt/solarna/secrets/cloudflare-tunnel-token`.

```bash
cd /opt/solarna
sudo chown 65532:65532 secrets/cloudflare-tunnel-token
sudo chmod 400 secrets/cloudflare-tunnel-token
docker compose --env-file .env.tunnel -f compose.tunnel.yaml \
  up --build -d --remove-orphans
docker compose --env-file .env.tunnel -f compose.tunnel.yaml ps
```

The Cloudflare hostname uses `http://127.0.0.1:8765`. The application and
connector share a private container network namespace to preserve that route.
