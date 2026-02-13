# Zip and Send — Full Harness Setup

Send the harness as a zip so recipients can get everything running with a single token prompt.

## For You (Sender)

1. **Create the zip:**
   ```powershell
   cd C:\Users\globa\harness
   Compress-Archive -Path * -DestinationPath harness.zip -Force
   ```

2. **Or push to GitHub** and share the repo link. Recipients can clone or download as zip.

## For Recipients

1. **Unzip** the harness (or clone the repo).

2. **Run bootstrap:**
   ```powershell
   cd harness
   .\bootstrap.ps1
   ```

3. **When prompted:**
   - "Set up OpenClaw? (y/N)" → type **y**
   - "OpenClaw token (API key or pairing code - leave blank to configure later)" → paste your token

4. **Done.** Bootstrap will:
   - Create harness directory structure
   - Save token to `.env` (ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENCLAW_TOKEN)
   - Create `~/.openclaw/openclaw.json` if it doesn't exist
   - Apply OpenClaw hardening (memory flash, Learning Loop, guardrails)
   - Copy all setup scripts

## Non-Interactive (Scripted)

For automation or CI:

```powershell
.\bootstrap.ps1 -OpenClawToken "sk-ant-xxx"
```

Skip OpenClaw setup entirely:

```powershell
.\bootstrap.ps1 -SkipOpenClaw
```

**If bootstrap.ps1 has parse errors** (PowerShell 5.1 / encoding): Run OpenClaw setup separately:

```powershell
.\scripts\openclaw_setup\bootstrap_openclaw.ps1 -TargetDir (Get-Location) -OpenClawToken "your-token"
```

## After Bootstrap

- **Restart OpenClaw** gateway to apply config changes
- **Verify:** `.\scripts\verify_harness.ps1`
- **OpenClaw setup later:** `python scripts\openclaw_setup\apply_openclaw_hardening.py`
