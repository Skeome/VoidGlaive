# Discord & Stoat Admin Bot

A general-purpose administrative bot available on two platforms:

- **`discord-bot.py`** — Discord, built with [disnake](https://github.com/DisnakeDev/disnake) (slash commands)
- **`stoat-bot.py`** — Stoat, built with [stoat.py](https://github.com/MCausc78/stoat.py) (prefix commands)

Both bots share the same `.env` file, virtual environment, and `requirements.txt`. Each maintains its own data directory (`discord/` and `stoat/` respectively) created automatically on first run.

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
├── discord-bot.py                  # Discord bot (disnake, slash commands)
├── stoat-bot.py            # Stoat bot (stoat.py, prefix commands)
├── requirements.txt        # Shared dependencies
├── dotenv-example.txt      # Copy to .env and fill in your values
├── config.example.json     # Documents the config.json schema
├── warnings.example.json   # Documents the warnings.json schema
│
├── discord/                # Auto-created on first run (Discord bot)
│   ├── config.json
│   ├── warnings.json
│   └── audit.log
│
└── stoat/                  # Auto-created on first run (Stoat bot)
    ├── config.json
    ├── warnings.json
    └── audit.log
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

### 5. Configure your bot accounts

#### Discord — Developer Portal settings

Before running, go to the [Discord Developer Portal](https://discord.com/developers/applications/), select your application, and open the **Bot** tab:

- Under **Privileged Gateway Intents**, enable:
  - **Server Members Intent** — required for member join/leave events and auto-role
  - **Message Content Intent** — required for prefix command processing
- Under **Bot Permissions**, ensure the permissions listed in [Required Bot Permissions](#required-bot-permissions) are granted when generating your invite link.

Without these intents enabled in the portal, the bot will crash on startup with a `PrivilegedIntentsRequired` error regardless of your code.

#### Stoat — Complete your bot's profile

Before running, log into [Stoat](https://stoat.chat), go to `My Bots` in your profile settings and **fully complete its profile** — set an avatar, bio, and banner. Stoat's onboarding check runs at the WebSocket authentication layer, and a bot with an incomplete profile will be rejected with a misleading `InvalidSession` error even if the token is valid.

### 6. Run the bot

**Discord bot:**
```bash
python discord-bot.py
```

**Stoat bot:**
```bash
python stoat-bot.py
```

On first run, each bot will automatically create its data directory (`discord/` or `stoat/`) containing `config.json`, `warnings.json`, and `audit.log`.

---

## Configuration

### Environment variables

| Variable | Required | Bot | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | for Discord | Discord | Bot token from the Discord Developer Portal |
| `STOAT_BOT_TOKEN` | for Stoat | Stoat | Bot token from your Stoat profile |
| `ADMIN_USER_IDS` | — | Discord | Comma-separated Discord user IDs with admin access |
| `STOAT_ADMIN_IDS` | — | Stoat | Comma-separated Stoat user IDs with admin access |
| `BOT_PREFIX` | — | Both | Command prefix (default: `!`) |
| `TEST_GUILD_ID` | — | Discord | Guild IDs for instant slash-command registration during dev |

To get a user or server ID, enable **Developer Mode** in your client settings, then right-click any user or server and select **Copy ID**.

### In-bot configuration (slash/prefix commands)

After the bot is running, use these commands to configure it per-server. Settings are saved to `config.json` and persist across restarts.

| Command | Description |
|---|---|
| `set_log_channel <channel>` | Channel where member join/leave and message events are posted |
| `set_autorole <role>` | Role automatically assigned to new members on join |
| `set_mute_role <role>` | Role applied by the `mute` command |

---

## Commands

### Discord (`discord-bot.py`) — Slash commands

| Command | Permission | Description |
|---|---|---|
| `/help` | Everyone | Lists all commands |
| `/ping` | Everyone | Bot latency |
| `/botinfo` | Everyone | Bot statistics |
| `/serverinfo` | Everyone | Server details |
| `/userinfo [member]` | Everyone | User details including warning count |
| `/avatar [member]` | Everyone | Displays a member's avatar |
| `/roleinfo <role>` | Everyone | Role details |
| `/warn <member> <reason>` | Manage Messages | Issue a warning |
| `/warnings <member>` | Manage Messages | View a member's warnings |
| `/clear_warnings <member>` | Administrator | Remove all warnings |
| `/kick <member> [reason]` | Kick Members | Kick a member |
| `/ban <member> [reason]` | Ban Members | Ban a member |
| `/unban <user_id> [reason]` | Ban Members | Unban by user ID |
| `/mute <member> [reason]` | Manage Roles | Apply the mute role |
| `/unmute <member>` | Manage Roles | Remove the mute role |
| `/purge <amount>` | Manage Messages | Bulk-delete up to 100 messages |
| `/slowmode <seconds>` | Manage Channels | Set channel slowmode (0 to disable) |
| `/lock` | Manage Channels | Block `@everyone` from sending messages |
| `/unlock` | Manage Channels | Restore `@everyone` send permissions |
| `/set_log_channel <channel>` | Administrator | Set the log channel |
| `/set_autorole <role>` | Administrator | Set the auto-role on join |
| `/set_mute_role <role>` | Administrator | Set the muted role |

### Stoat (`stoat-bot.py`) — Prefix commands (default prefix: `!`)

Same command set as above, using `!command` syntax instead of slash commands, plus:

| Command | Permission | Description |
|---|---|---|
| `!status` | Admin | Bot statistics and config summary |
| `!shutdown` | Admin | Gracefully shut down the bot |

---

## Required Bot Permissions

When inviting either bot to a server, grant the following permissions:

- Manage Roles
- Kick Members
- Ban Members
- Manage Channels
- Manage Messages
- Read Messages / View Channels
- Send Messages
- Embed Links *(Discord only)*

---

## Data Files

The `config.example.json` and `warnings.example.json` files in the root document the schema of the JSON files each bot writes. You do not need to create or edit these manually — the bots create and manage them automatically.

The `audit.log` in each data directory records all moderation actions (warn, kick, ban, unban, mute, unmute, purge, slowmode, lock, unlock, and config changes) with timestamps, guild IDs, and user IDs.

---

## NixOS Notes

If running as a systemd service on NixOS, ensure the `.env` variables are loaded into the service environment, or export them in the shell before running. The virtual environment approach above works without any NixOS-specific configuration.