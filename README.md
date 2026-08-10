# Productif Ops Bot

Telegram bot for daily productif.io team execution.

The bot sends each person a morning plan, lets them mark tasks as done, blocked, or not done, and creates an evening recap from actual check-ins.

## MVP scope

- Telegram commands:
  - `/start noah`
  - `/plan`
  - `/done PIO-001 proof: screenshot sent`
  - `/blocked PIO-002 reason: no Buffer access`
  - `/notdone PIO-003 reason: no time slot`
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
/start noah
```

Valid people in the MVP:

- `noah`
- `gaetan`
- `arthur`

### See your plan

```text
/plan
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

## Suggested development order

1. Run locally with Noah only.
2. Validate `/plan`, `/done`, `/blocked`, `/notdone`, `/recap`.
3. Replace sample tasks with real productif.io tasks.
4. Deploy to VPS with systemd.
5. Add Gaetan and Arthur.
6. Add AI plan generation.

## VPS deployment later

Create a dedicated Linux user, clone the repo, configure `.env`, then run the service with systemd. Do not deploy before the local bot works.

## AI worker later

The AI worker should read:

- tasks from SQLite;
- check-ins from SQLite;
- SOPs from `sops/`;
- productif.io roadmap context.

It should output a proposed plan for tomorrow. It should not send Telegram messages directly or deploy productif.io.
