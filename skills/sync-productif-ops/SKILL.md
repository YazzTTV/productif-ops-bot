---
name: sync-productif-ops
description: Inspect a teammate's current work folder, retrieve their assigned Productif Ops tasks and SOPs, prepare evidence-backed task status updates, and synchronize approved check-ins with the Productif Telegram bot. Use when Noah, Gaetan, or Arthur asks for their Productif plan, says they are ending a work session, wants to report completed or blocked work, or asks to sync/update Telegram from their Cowork workspace.
---

# Sync Productif Ops

Use the bundled `scripts/productif_ops_sync.py` client. Resolve its path relative to this `SKILL.md`; never copy the script into the user's project.

## Read the plan

Run `python3 <script> plan --json` before mapping work to tasks. The default plan is the shared team view so every associate can see global priorities and ownership. Use `--mine` for only the authenticated teammate's open tasks, or `--due` for only their tasks due today or overdue. Read task descriptions and SOPs returned by the API.

If configuration is missing, stop and ask for the public HTTPS API URL, the teammate identity (`noah`, `gaetan`, or `arthur`), and their personal API token. Tell them to configure it locally with:

```bash
python3 <script> configure --api-url https://ops.example.com --person gaetan
```

The command prompts for the token without displaying it and stores credentials with file mode `0600`. Never print, commit, quote, or send the token to Telegram.

## Prepare an end-of-session sync

1. Retrieve the shared team plan with `plan --json`, then identify tasks owned by the authenticated teammate.
2. Inspect only the current work folder. For Git projects, use status, diff statistics, recent commits, tests, and explicit output links as evidence. For non-Git folders, inspect relevant recently modified files.
3. Map evidence only to task IDs assigned to the configured teammate.
4. Classify each reported task:
   - `done`: acceptance criteria are met; include concrete proof.
   - `in_progress`: meaningful work exists but acceptance criteria are not complete.
   - `blocked`: progress requires an external decision, access, dependency, or fix; include the blocker.
   - `not_done`: the task was not completed in this session; include the reason.
5. Do not infer `done` from a changed file alone. Run relevant checks when possible and treat a commit hash, published URL, screenshot reference, test result, or delivered artifact as proof.
6. Ignore unrelated local changes and never upload source contents or secrets. The client sends only the status text and compact workspace metadata.

## Require approval

Build a dry run first. Example:

```bash
python3 <script> submit --workspace . \
  --done CONT-002 \
  --proof "CONT-002=Buffer link and exported C01-C08" \
  --blocked CONT-004 \
  --message "CONT-004=TikTok access is missing" \
  --summary "Carousels delivered; outlier research blocked"
```

Present the exact task IDs, statuses, reasons, and proofs to the user. Do not mutate Productif Ops until the user explicitly approves this proposed sync.

After approval, rerun the same command with `--confirm`. Report the returned sync run ID and whether Telegram notification succeeded. If the API rejects an update, preserve the local work, explain the exact validation error, and do not retry with weaker proof.

## Guardrails

- Keep the full team plan visible, but update only tasks assigned to the authenticated teammate. Ask for reassignment when someone takes over another person's task.
- Never create, reassign, cancel, or edit another person's tasks.
- Never mark proof-required work done without concrete proof.
- Never expose the Telegram bot token; teammates use only their revocable personal API token.
- Never deploy, publish, message external customers, or modify project files as part of synchronization unless the user separately requested that work.
