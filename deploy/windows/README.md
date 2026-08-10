# Windows services

The live deployment runs on Windows, so `deploy/systemd/` does not apply. These
three files are the WinSW service definitions actually in use. They were first
written by hand directly on the host, which meant the deployment configuration
existed nowhere but that machine; they live here so it can be rebuilt.

Copy them next to their WinSW executables, then install:

```powershell
Copy-Item C:\productif-ops-bot\deploy\windows\*.xml C:\productif-ops-bot\services\
Set-Location C:\productif-ops-bot\services

.\productif-ops-api-service.exe install
.\productif-ops-bot-service.exe install
.\productif-ops-caddy-service.exe install
```

Each `<id>` must match the base name of its WinSW copy: WinSW looks for the XML
sitting beside the executable that runs it.

## Why PYTHONUNBUFFERED is set

Python block-buffers stdout and stderr as soon as they are redirected to a file
rather than a terminal. WinSW redirects them to `logs\`, so log lines stayed in
the buffer and the log looked empty while requests were actually being served.
That made two failures invisible: a Telegram notification that could not be
delivered, and a nightly backup that raised. Both are logged, and neither
reached the disk. Caddy writes its own output and does not need the variable.

## Reading the logs

```powershell
Get-Content C:\productif-ops-bot\logs\productif-ops-api-service.err.log -Tail 40 -Wait
```

Python's `logging.basicConfig` writes to stderr, so the interesting lines are in
`.err.log`, not `.out.log`, including ordinary INFO lines.
