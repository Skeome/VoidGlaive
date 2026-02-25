# Stoat Admin Bot

A general-purpose administrative bot available on Stoat:

- **`stoat-bot.py`** built with [stoat.py](https://github.com/MCausc78/stoat.py)

Bot uses an `.env` file, and a virtual environment (`.venv`) that can be setup using `requirements.txt`. It maintains its own data directory (`stoat/`) created automatically on first run.

---

## Features

- Moderation: kick, ban, unban, mute, unmute, purge, slowmode, lock/unlock
- Warning system with persistent storage (`warnings.json`)
- Member join/leave and message edit/delete event logging to a configured channel
- Auto-role assignment on member join
- Per-guild configuration: log channel, mute role, auto-role (`config.json`)
- Audit log of all moderation actions (`audit.log`)
- Admin access controlled via environment variables

---

## File Structure

```
.
├── stoat-bot.py            # Stoat bot (stoat.py, prefix commands)
├── requirements.txt        # Bot Dependencies
├── dotenv-example.txt      # Copy to .env and fill in your values
│
│
└── stoat/                  # Auto-created on first run (Stoat bot)
    ├── config.json         # When you run commands, these files
    ├── warnings.json       # get updated automatically, depending
    └── audit.log           # on the command
```

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Skeome/VoidGlaive.git
cd VoidGlave
```

### 2. Create and activate a virtual environment

**NixOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Linux / macOS**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (Command Prompt)**
```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp dotenv-example.txt .env
```

Open `.env` and fill in your values. See the [Configuration](#configuration) section below for details.

### 5. Configure your bot account

#### Complete your bot's profile

Before running, log into [Stoat](https://stoat.chat), go to `My Bots` in your profile settings and **fully complete its profile**. Set an avatar, bio, and banner. Stoat's onboarding check runs at the WebSocket authentication layer, and a bot with an incomplete profile will be rejected with a misleading `InvalidSession` error even if the token is valid.

### 6. Run the bot

**Stoat bot:**
```bash
python stoat-bot.py
```

On first run, the bot will automatically create its data directory (`stoat/`) containing `config.json`, `warnings.json`, and `audit.log`.

You do not need to create or edit these manually; the bots create and manage them automatically.
The `audit.log` in the data directory records all moderation actions (warn, kick, ban, unban, mute, unmute, purge, slowmode, lock, unlock, and config changes) with timestamps, Server IDs, and user IDs.


---

## Configuration

### Environment variables

| Variable | Required | Description |
|---|---|---|
| `STOAT_BOT_TOKEN` | Yes | Bot token from your Stoat profile |
| `STOAT_ADMIN_IDS` | Optional | Comma-separated Stoat user IDs with admin access |
| `BOT_PREFIX` | Optional | Command prefix (default: `!`) |


To get a User or Server ID, enable **Developer Mode** in your client settings, then right-click any user or server and select **Copy ID**.

### In-bot configuration (prefix commands)

After the bot is running, use these commands to configure it per-server. Settings are saved to `config.json` and persist across restarts.

| Command | Description |
|---|---|
| `!set_log_channel <channel>` | Channel where member join/leave and message events are posted |
| `!set_autorole <role>` | Role automatically assigned to new members on join |
| `!set_mute_role <role>` | Role applied by the `mute` command |

---

## Commands

| Command | Permission | Description |
|---|---|---|
| `!help` | Everyone | Lists all commands |
| `!ping` | Everyone | Bot latency |
| `!avatar [member]` | Everyone | Displays a member's avatar |
| `!botinfo` | Administrator | Bot statistics |
| `!roleinfo <role>` | Administrator | Role details |
| `!serverinfo` | Administrator | Server details |
| `!userinfo [member]` | Administrator | User details including warning count |
| `!warn <member> <reason>` | Administrator | Issue a warning |
| `!warnings <member>` | Everyone | View a member's warnings |
| `!clear_warnings <member>` | Administrator | Remove all warnings |
| `!kick <member> [reason]` | Administrator | Kick a member |
| `!ban <member> [reason]` | Administrator | Ban a member |
| `!unban <user_id> [reason]` | Administrator | Unban by user ID |
| `!mute <member> [reason]` | Administrator | Apply the mute role |
| `!unmute <member>` | Administrator | Remove the mute role |
| `!purge <amount> [member]` | Administrator | Bulk-delete up to 100 messages |
| `!lock` | Administrator | Block members from sending messages |
| `!unlock` | Administrator | Restore member send permissions |
| `!set_log_channel <channel>` | Administrator | Set the log channel |
| `!set_autorole <role>` | Administrator | Set the auto-role on join |
| `!set_mute_role <role>` | Administrator | Set the muted role |
| `!status` | Administrator | Bot statistics and config summary |
| `!shutdown` | Administrator | Gracefully shut down the bot |

---

## Required Bot Permissions

When inviting the bot to a server, grant the following permissions:

**Update:** Permissions must be set per channel for `lock` and `unlock`. (only the channels you want locked need these permissions set to true. Server overrides do not affect channel perms)

- Manage Roles
- Kick Members
- Ban Members
- Manage Channels
- Manage Messages
- Read Messages / View Channels
- Send Messages

---

## NixOS Notes

If running as a systemd service on NixOS, ensure the `.env` variables are loaded into the service environment, or export them in the shell before running. The virtual environment approach above works without any NixOS-specific configuration.
