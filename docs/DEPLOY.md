# Deploying RoomBook at home (Proxmox)

This guide takes you from a Proxmox host to a booking site your staff can
reach from anywhere, with automatic HTTPS.

There are two ways to expose it to the internet. **Read both before picking:**

| | A. Direct (DNS + open ports) | B. Cloudflare Tunnel |
|---|---|---|
| Open ports on your router | 80 + 443 | **None** |
| Works for IPv4-only visitors | Only if you have a public IPv4 / port-forward | **Yes** |
| Extra account needed | No | Free Cloudflare account |
| Certificates | Automatic (Caddy/Let's Encrypt) | Automatic (Cloudflare) |

Option B is usually the better fit for a home server: many workplace and
guest networks are still IPv4-only, so an IPv6-only direct setup would be
unreachable for some staff, and a tunnel means no inbound ports open on your
home connection at all.

## 1. Create the VM/container on Proxmox

A small Debian 12/13 VM is the least-friction option for running Docker:

- 1–2 vCPU, 1–2 GB RAM, 8–10 GB disk is plenty for this app.
- (LXC also works, but Docker-in-LXC needs a privileged container or extra
  keyctl/nesting options — a VM avoids that faff entirely.)

Install Docker inside it:

```bash
curl -fsSL https://get.docker.com | sh
```

Clone this repository onto the VM:

```bash
git clone https://github.com/KingJulian101/Test.git roombook
cd roombook
cp .env.example .env
```

Edit `.env`: set a real `SECRET_KEY` (`openssl rand -hex 32`), your domain,
and the initial admin username/password.

## 2a. Option A — direct exposure (DNS + IPv6/IPv4)

1. **DNS.** Buy/use a domain and create an `AAAA` record pointing at the
   VM's *global* IPv6 address (get it with `ip -6 addr`; it should not start
   with `fd` or `fe80`). If your ISP also gives you a public IPv4, add an `A`
   record and a port-forward of 80/443 to the VM.
2. **Firewall.** Allow inbound TCP 80 and 443 to the VM in your
   router/firewall's IPv6 rules (and IPv4 port-forwards if applicable).
   If your ISP rotates your IPv6 prefix, set up a dynamic-DNS updater or
   prefer Option B.
3. **Start it:**

   ```bash
   docker compose up -d --build
   ```

   Caddy will fetch a Let's Encrypt certificate for `DOMAIN` automatically
   (the domain must already resolve to the VM before first start).

Remember the IPv6 caveat: staff on IPv4-only networks (some corporate/NHS
networks, some mobile carriers) cannot reach an IPv6-only site.

## 2b. Option B — Cloudflare Tunnel (recommended, no open ports)

1. Add your domain to a free Cloudflare account.
2. In **Zero Trust → Networks → Tunnels**, create a tunnel, name it, and
   copy the token.
3. Run the app *without* the bundled Caddy (the tunnel provides HTTPS):

   ```bash
   docker compose up -d --build app
   docker run -d --restart unless-stopped --network roombook_default \
     cloudflare/cloudflared:latest tunnel --no-autoupdate run --token <TOKEN>
   ```

4. In the tunnel's **Public Hostname** settings, map
   `rooms.yourdomain.co.uk` → `http://app:8000`.
5. Optional but recommended: add a Cloudflare Access policy in front of it
   (e.g. restrict to your staff email domain) for a second layer of login.

The tunnel is outbound-only from your VM, works over your IPv6 connection,
and visitors reach it over IPv4 or IPv6 regardless.

## 3. First login

Browse to your domain, log in with the admin account from `.env`, then:

1. **Rooms** — rename `Room 1`–`Room 10` to your real room names, set
   capacities, drag the ordering via the sort field.
2. **Users** — add your staff (they can change their password under their
   own account page).

## 4. Backups

Everything lives in one SQLite file in the `app_data` volume. Nightly backup
to the host (add to `crontab -e` on the VM):

```cron
15 2 * * * docker compose -f /root/roombook/docker-compose.yml exec -T app sqlite3 /data/roombook.sqlite ".backup /data/backup.sqlite" && docker cp $(docker compose -f /root/roombook/docker-compose.yml ps -q app):/data/backup.sqlite /root/backups/roombook-$(date +\%a).sqlite
```

(Or simply snapshot the whole VM from Proxmox on a schedule — Proxmox Backup
Server or `vzdump` both work well.) Test a restore once before you rely on it.

## 5. Updates

```bash
cd /root/roombook
git pull
docker compose up -d --build
```

## 6. Security checklist

- [ ] `SECRET_KEY` is long and random; admin password is strong.
- [ ] HTTPS only (Caddy or Cloudflare handles this — never expose port 8000 directly).
- [ ] Keep the VM patched (`unattended-upgrades` on Debian) and update the containers occasionally.
- [ ] Logins are throttled (5 failures / 15 min) but consider Cloudflare Access or an IP allow-list for defence in depth.
- [ ] Policy: no patient-identifiable data in booking titles/notes — bookings are visible to all logged-in staff.
- [ ] Backups exist and a restore has been tested.
