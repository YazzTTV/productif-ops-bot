# Productif Ops Bot

Telegram bot for daily productif.io team execution.

The bot sends each person a morning plan, lets them mark tasks as done, blocked, or not done, and creates an evening recap from actual check-ins.

## MVP scope

- Telegram commands:
  - `/start noah`
  - `/plan`
  - `/tasks open`
  - `/task PIO-001`
  - `/done PIO-001 proof: screenshot sent`
  - `/blocked PIO-002 reason: no Buffer access`
  - `/notdone PIO-003 reason: no time slot`
  - `/setstatus PIO-001 done proof: handled by Noah`
  - `/assign PIO-001 gaetan`
  - `/recap`
  - `/sop PIO-001`
- SQLite source of truth.
- Morning and evening scheduled messages.
- Markdown SOP files linked to tasks.
- No AI in V0. AI comes after the operating loop works.

## Local setup

Create the bot with BotFather on Telegram:

1. Open Telegram.
2. Message `@BotFather`.
3. Run `/newbot`.
4. Copy the bot token.

Install locally:

```bash
cd /Users/noah/Documents/dev/productif-ops-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```

Edit `.env` and set:

```text
TELEGRAM_BOT_TOKEN=...
```

Run:

```bash
productif-ops-bot
```

In Telegram, open the bot and send:

```text
/start noah
/plan
```

## Commands

### Register

```text
/start noah rentree2026
```

The second argument is the value of `OPS_ENROLL_CODE`. It is required as soon as
that variable is set, and it is what stops a stranger who finds the bot from
claiming an unclaimed identity and reading the whole team plan. Without the
variable the command stays `/start noah`, and the bot logs a warning at startup.

Valid people in the MVP:

- `noah`
- `gaetan`
- `arthur`

### See your plan

```text
/plan
```

`/plan` shows open tasks due today or overdue. Use `/tasks` for the full backlog.

### See team tasks

```text
/tasks
/tasks all
/tasks blocked
/tasks open gaetan
```

### See one task

```text
/task PIO-001
```

### Mark done

```text
/done PIO-001 proof: tested on iPhone
```

### Mark blocked

```text
/blocked PIO-002 reason: no Buffer access
```

### Mark not done

```text
/notdone PIO-003 reason: no available slot
```

### See recap

```text
/recap
```

### Read linked SOP

```text
/sop PIO-001
```

### Add a task

Noah only in the MVP.

```text
/addtask owner:noah title:Soumettre TestFlight priority:P0 due:2026-08-13 sop:app-store-submit.md proof:true
```

Required fields:

- `owner`
- `title`
- `priority`
- `due`

Optional fields:

- `id`
- `sop`
- `description`
- `proof:true`

### Admin status change

Noah only in the MVP.

```text
/setstatus PIO-001 done proof: handled manually
```

### Assign a task

Noah only in the MVP.

```text
/assign PIO-001 gaetan
```

## Suggested development order

1. Run locally with Noah only.
2. Validate `/plan`, `/done`, `/blocked`, `/notdone`, `/recap`.
3. Replace sample tasks with real productif.io tasks.
4. Deploy to VPS with systemd.
5. Add Gaetan and Arthur.
6. Add AI plan generation.

## Load the real productif.io plan

The repo includes a curated seed built from the productif.io vault and weekly recap.

```bash
productif-ops-import-plan
```

It loads tasks from:

```text
seeds/productif_plan_2026_08_10.json
```

By default, this seed archives old open sample tasks that are not part of the real plan. Existing seed tasks keep their current status when reimported, so rerunning the import does not reset work already marked done or blocked.

## Deployment, as actually done

The live instance runs on a **Windows** machine, so `deploy/systemd/` is unused.
Three WinSW services, all auto-start with restart-on-failure:

```text
ProductifOpsApi     .venv\Scripts\productif-ops-api.exe    bound to 127.0.0.1:8787
ProductifOpsBot     .venv\Scripts\productif-ops-bot.exe
ProductifOpsCaddy   caddy.exe run --config C:\caddy\Caddyfile
```

Caddy terminates HTTPS for `ops.productif.io` and reverse-proxies to the API.
The host's IPv4 is shared and does not forward 80/443, so the public entry point
is **IPv6**, plus a shared SNI pass-through IPv4 frontend for clients without
IPv6. Both DNS records are required:

```text
AAAA  ops  -> the host's global IPv6
A     ops  -> the IPv4 frontend of the provider
```

Two consequences worth knowing before debugging an outage. The host sits on a
residential line, so its IPv6 prefix is not guaranteed static: if it changes the
`AAAA` record goes stale and the API dies with no error anywhere. And never run
the bot locally while the service is running, since two pollers on one token
produce a loop of Telegram `409 Conflict`.

Backups: the bot snapshots the database every day at 23:30 into
`data/backups/`, keeping the last 14. That directory is git-ignored, so copy it
off the machine periodically. The database is the source of truth of the tool.

## AI worker later

The AI worker should read:

- tasks from SQLite;
- check-ins from SQLite;
- SOPs from `sops/`;
- productif.io roadmap context.

It should output a proposed plan for tomorrow. It should not send Telegram messages directly or deploy productif.io.

## Cowork folder sync

The repo includes the shareable `sync-productif-ops` skill. Every associate can read the shared team plan, priorities, ownership and SOPs. At the end of a work session, each teammate sends approved statuses and compact workspace evidence for their assigned tasks.

The teammate never receives the Telegram bot token. Each person gets a revocable API token. The shared plan stays visible to everyone, while every write is attributed and limited to tasks assigned to that identity; reassign a task first when ownership changes.

Start the API locally in a second terminal:

```bash
source .venv/bin/activate
productif-ops-api
```

Create one token per teammate. The raw value is displayed once:

```bash
productif-ops-token create gaetan --label gaetan-macbook
productif-ops-token create arthur --label arthur-macbook
productif-ops-token list
```

Install the skill on a teammate's Mac:

```bash
mkdir -p ~/.codex/skills
cp -R skills/sync-productif-ops ~/.codex/skills/
```

Restart Codex, then configure the skill. The token prompt is hidden:

```bash
python3 ~/.codex/skills/sync-productif-ops/scripts/productif_ops_sync.py \
  configure --api-url https://ops.example.com --person gaetan
```

They can then ask Cowork to use `$sync-productif-ops`, or run the client directly:

```bash
python3 ~/.codex/skills/sync-productif-ops/scripts/productif_ops_sync.py plan
```

Every submission is a dry run unless `--confirm` is present. The skill must show the proposed updates and obtain explicit approval before rerunning with `--confirm`.

### VPS API

Run the Telegram bot and API as separate systemd services using the templates in `deploy/systemd/`. Keep `OPS_API_HOST=127.0.0.1`; expose it through HTTPS with Caddy or another reverse proxy. `deploy/Caddyfile.example` contains the minimal Caddy route.

After the public HTTPS health check works, generate Gaetan and Arthur's tokens on the VPS. Send each token privately and never commit it or paste it in a shared chat.
