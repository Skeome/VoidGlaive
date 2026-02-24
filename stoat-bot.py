import stoat
import stoat.abc
from stoat.ext import commands
import json
import datetime
import zoneinfo
import os
import sys
import asyncio
from typing import Optional, Dict, List, cast
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ==============================================================================
# --- Configuration ---
# ==============================================================================

BOT_TOKEN  = os.getenv("STOAT_BOT_TOKEN")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

# Comma-separated Stoat User IDs with elevated bot-level admin access
admin_ids_str  = os.getenv("STOAT_ADMIN_IDS", "")
ADMIN_USER_IDS = [uid.strip() for uid in admin_ids_str.split(",") if uid.strip()]

MAX_MESSAGE_LENGTH = 2000  # Stoat message length limit

# ==============================================================================
# --- File / Directory Paths ---
# ==============================================================================

DATA_DIR       = "stoat"
AUDIT_LOG_PATH = os.path.join(DATA_DIR, "audit.log")
WARNINGS_FILE  = os.path.join(DATA_DIR, "warnings.json")
CONFIG_FILE    = os.path.join(DATA_DIR, "config.json")

# ==============================================================================
# --- In-memory state (loaded from disk at startup) ---
# ==============================================================================

# { "server_id:user_id": [ {reason, mod_tag, mod_id, timestamp}, ... ] }
warnings: Dict[str, List[Dict]] = {}

# { "server_id": { "log_channel_id": str, "mute_role_id": str, "autorole_id": str } }
server_cfg: Dict[str, Dict] = {}


# ==============================================================================
# --- Helpers ---
# ==============================================================================

def setup_file_structure() -> None:
    """Creates the stoat/ directory and persistent JSON files if they do not exist."""
    os.makedirs(DATA_DIR, exist_ok=True)
    for path, default in [(WARNINGS_FILE, {}), (CONFIG_FILE, {})]:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
    if not os.path.exists(AUDIT_LOG_PATH):
        with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
            f.write(f"# Audit Log — created {_now()}\n\n")


def _now() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def audit(action: str, server_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """Writes a timestamped moderation entry to the audit log and stdout."""
    parts = [f"[{_now()}]", action]
    if server_id:
        parts.append(f"server:{server_id}")
    if user_id:
        parts.append(f"user:{user_id}")
    line = "  ".join(parts)
    print(line)
    try:
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"[WARN] audit log write failed: {e}")


def load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[WARN] Could not load {path}: {e}")
        return {}


def save_json(path: str, data: dict) -> None:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Could not save {path}: {e}")


def load_all() -> None:
    global warnings, server_cfg
    warnings   = load_json(WARNINGS_FILE)
    server_cfg = load_json(CONFIG_FILE)


def warning_key(server_id: str, user_id: str) -> str:
    return f"{server_id}:{user_id}"


def cfg(server_id: str) -> Dict:
    """Returns the config dict for a server, creating it if absent."""
    return server_cfg.setdefault(str(server_id), {})


def is_admin():
    """Check decorator for admin permissions."""
    async def predicate(ctx):
        return str(ctx.author.id) in ADMIN_USER_IDS
    return commands.check(predicate)


def parse_user_id(argument: str) -> Optional[str]:
    """Extracts a user ID from a raw ID string or a <@ID> mention."""
    argument = argument.strip()
    if argument.startswith("<@") and argument.endswith(">"):
        argument = argument[2:-1]
    return argument if argument and argument.isalnum() else None


def get_server_id(ctx) -> str:
    """Extracts server ID from context via message. Returns 'DM' if not in a server."""
    _, server_id = ctx.message.get_server()
    return server_id if server_id else "DM"


async def send_long_message(ctx, title: str, content: str) -> None:
    """Sends a message, splitting into chunks if content exceeds the Stoat limit."""
    header = f"**{title}**\n" if title else ""
    if len(header) + len(content) <= MAX_MESSAGE_LENGTH:
        await ctx.send(f"{header}{content}")
        return
    chunk_size = 1500
    chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
    await ctx.send(f"{header}(Part 1/{len(chunks)})")
    for i, chunk in enumerate(chunks):
        prefix = "" if i == 0 else f"(Part {i + 1}/{len(chunks)})\n"
        await ctx.send(f"{prefix}{chunk}")


async def post_to_log(server_id: str, message: str) -> None:
    """Posts a plain-text message to the configured log channel if set."""
    log_ch_id = cfg(server_id).get("log_channel_id")
    if not log_ch_id:
        return
    ch = bot.get_channel(log_ch_id)
    if ch and isinstance(ch, stoat.abc.Messageable):
        try:
            await ch.send(message)
        except Exception as e:
            print(f"[WARN] Could not post to log channel: {e}")


# ==============================================================================
# --- Bot Class ---
# ==============================================================================

class AdminBot(commands.Bot):

    async def on_ready(self, event):
        user_name = self.user.name if self.user else "Bot"
        user_id   = self.user.id   if self.user else "?"
        print(f"\n✅  Logged in as {user_name}  (ID: {user_id})")
        print(f"   Prefix : {BOT_PREFIX}\n")
        audit(f"Bot online  tag={user_name}  id={user_id}")

    async def on_server_member_join(self, event):
        member    = event.member
        server_id = str(member.server_id)

        # Auto-role
        role_id = cfg(server_id).get("autorole_id")
        if role_id:
            try:
                current_roles = list(member.role_ids) if member.role_ids else []
                if role_id not in current_roles:
                    await member.edit(roles=cast(list, current_roles + [role_id]))
            except Exception as e:
                print(f"[WARN] Could not assign auto-role: {e}")

        await post_to_log(
            server_id,
            f"📥 **Member Joined:** `{member.user}`  (ID: {member.user.id})"
        )

    async def on_server_member_remove(self, event):
        server_id = str(event.server_id)
        user_id   = str(event.user_id)
        member    = event.member
        display   = f"`{member.user}`  (ID: {user_id})" if member else f"ID: {user_id}"
        await post_to_log(
            server_id,
            f"📤 **Member Left:** {display}"
        )

    async def on_message_delete(self, event):
        message = event.message
        if not message:
            return
        _, server_id = message.get_server()
        if not server_id:
            return
        content_preview = message.content[:500] if message.content else "*(no text content)*"
        await post_to_log(
            server_id,
            f"🗑️ **Message Deleted** in <#{event.channel_id}> by {message.author.mention}\n"
            f"```{content_preview}```"
        )

    async def on_message_update(self, event):
        before = event.before
        after  = event.after
        if not before or not after:
            return
        if before.content == after.content:
            return
        _, server_id = after.get_server()
        if not server_id:
            return
        await post_to_log(
            server_id,
            f"✏️ **Message Edited** in <#{after.channel_id}> by {after.author.mention}\n"
            f"**Before:** {before.content[:300]}\n"
            f"**After:** {after.content[:300]}"
        )

    async def on_message_create(self, event):
        message = event.message
        shard   = event.shard
        if self.user and message.author.id == self.user.id:
            return
        await self.process_commands(message, shard)

    async def on_command_error(self, event):
        ctx   = event.context
        error = event.error
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.CheckFailure):
            await ctx.send("❌ You don't have permission to use that command.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing required argument: `{str(error)}`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"⚠️ Bad argument: {error}")
        elif isinstance(error, stoat.NoData):
            await ctx.send("❌ Could not retrieve that user's data from cache — try again.")
        else:
            print(f"[ERROR] command={ctx.command}  {error}")
            await ctx.send("⚠️ An unexpected error occurred.")


bot = AdminBot(command_prefix=BOT_PREFIX)


# ==============================================================================
# --- Commands: Information ---
# ==============================================================================

@bot.command(name="help")
async def show_help(ctx: commands.Context):
    """Displays all available commands."""
    help_text = f"""**📖 Command Reference**  (prefix: `{BOT_PREFIX}`)

**ℹ️ Information**
`{BOT_PREFIX}help` — This message
`{BOT_PREFIX}ping` — Bot latency
`{BOT_PREFIX}botinfo` — Bot statistics
`{BOT_PREFIX}userinfo [@member]` — User details

**⚠️ Warnings**
`{BOT_PREFIX}warn <@mention|ID> <reason>` — Warn a member
`{BOT_PREFIX}warnings <@mention|ID>` — View a member's warnings
`{BOT_PREFIX}clear_warnings <@mention|ID>` — Remove all warnings  *(Admin)*

**🔨 Moderation**
`{BOT_PREFIX}kick <@mention|ID> [reason]` — Kick a member
`{BOT_PREFIX}ban <@mention|ID> [reason]` — Ban a member
`{BOT_PREFIX}unban <@mention|ID>` — Unban a user by ID
`{BOT_PREFIX}mute <@mention|ID> [reason]` — Apply the mute role
`{BOT_PREFIX}unmute <@mention|ID>` — Remove the mute role

**⚙️ Admin Config**  *(Admin only)*
`{BOT_PREFIX}set_log_channel <channel_id>` — Set the log channel
`{BOT_PREFIX}set_autorole <role_id>` — Set the auto-role on join
`{BOT_PREFIX}set_mute_role <role_id>` — Set the muted role
`{BOT_PREFIX}status` — Bot status and statistics
`{BOT_PREFIX}shutdown` — Shut down the bot"""
    await send_long_message(ctx, "", help_text)


@bot.command(name="ping")
async def ping(ctx: commands.Context):
    """Check the bot's latency."""
    await ctx.send("🏓 Pong!")


@bot.command(name="botinfo")
async def botinfo(ctx: commands.Context):
    """Display statistics about the bot."""
    user_id = bot.user.id if bot.user else "?"
    await ctx.send(
        f"🤖 **Bot Info**\n"
        f"Prefix: `{BOT_PREFIX}`\n"
        f"ID: `{user_id}`\n"
        f"Admin IDs loaded: {len(ADMIN_USER_IDS)}"
    )


@bot.command(name="userinfo")
async def userinfo(ctx: commands.Context, user_arg=""):
    """Display information about a user. Accepts a mention or user ID (or no argument for yourself)."""
    sid = get_server_id(ctx)
    if not user_arg:
        user = ctx.author
        uid  = str(user.id)
    else:
        uid = parse_user_id(user_arg)
        if not uid:
            return await ctx.send("❌ Invalid user — provide a mention or user ID.")
        try:
            user = await bot.fetch_user(uid)
        except Exception:
            return await ctx.send(f"❌ Could not find user with ID `{uid}`.")
    wcount = len(warnings.get(warning_key(sid, uid), []))
    await ctx.send(
        f"👤 **{user}**\n"
        f"ID: `{uid}`\n"
        f"Warnings: {wcount}"
    )


# ==============================================================================
# --- Commands: Warnings ---
# ==============================================================================

@bot.command(name="warn")
@is_admin()
async def warn(ctx: commands.Context, user_arg, *, reason):
    """Issue a warning to a member. Accepts a mention or user ID."""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find user with ID `{uid}`.")
    sid = get_server_id(ctx)
    key = warning_key(sid, uid)
    warnings.setdefault(key, []).append({
        "reason":    reason,
        "mod_id":    str(ctx.author.id),
        "mod_tag":   str(ctx.author),
        "timestamp": _now(),
    })
    save_json(WARNINGS_FILE, warnings)
    total = len(warnings[key])

    try:
        await user.send(
            f"⚠️ You have been warned.\n"
            f"Reason: {reason}\nTotal warnings: {total}"
        )
    except Exception:
        pass

    await ctx.send(f"⚠️ {user.mention} warned.  Reason: {reason}  (Total: {total})")
    audit(f"warn  target={uid}  reason={reason!r}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(
        sid,
        f"⚠️ **Member Warned**\nMember: {user} (`{uid}`)\nMod: {ctx.author}\n"
        f"Reason: {reason}\nTotal warnings: {total}"
    )


@bot.command(name="warnings")
async def view_warnings(ctx: commands.Context, user_arg):
    """View warnings for a member. Accepts a mention or user ID."""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find user with ID `{uid}`.")
    sid   = get_server_id(ctx)
    wlist = warnings.get(warning_key(sid, uid), [])
    if not wlist:
        return await ctx.send(f"ℹ️ {user.mention} has no warnings.")
    lines = "\n".join(
        f"#{i}  [{w['timestamp']}]  Reason: {w['reason']}  (Mod: {w['mod_tag']})"
        for i, w in enumerate(wlist, 1)
    )
    await send_long_message(ctx, f"⚠️ Warnings for {user}  ({len(wlist)})", lines)


@bot.command(name="clear_warnings")
@is_admin()
async def clear_warnings(ctx: commands.Context, user_arg):
    """Remove all warnings for a member. Accepts a mention or user ID. (Admin only)"""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find user with ID `{uid}`.")
    sid = get_server_id(ctx)
    key = warning_key(sid, uid)
    if key in warnings:
        del warnings[key]
        save_json(WARNINGS_FILE, warnings)
        await ctx.send(f"✅ All warnings cleared for {user.mention}.")
    else:
        await ctx.send(f"ℹ️ {user.mention} has no warnings to clear.")
    audit(f"clear_warnings  target={uid}", server_id=sid, user_id=str(ctx.author.id))


# ==============================================================================
# --- Commands: Moderation ---
# ==============================================================================

@bot.command(name="kick")
@is_admin()
async def kick(ctx: commands.Context, user_arg, *, reason="No reason provided."):
    """Kick a member from the server. Accepts a mention or user ID. (Admin only)"""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    if uid == str(ctx.author.id):
        return await ctx.send("❌ You cannot kick yourself.")
    sid = get_server_id(ctx)
    if sid == "DM":
        return await ctx.send("❌ This command can only be used in a server.")
    try:
        server = await bot.fetch_server(sid)
        member = await server.fetch_member(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find member `{uid}` in this server.")
    # Fetch user independently so we have it cached before kicking
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        user = None
    try:
        await (user or member.user).send(f"👢 You have been kicked.\nReason: {reason}")
    except Exception:
        pass
    try:
        await member.kick()
    except Exception:
        return await ctx.send("❌ I don't have permission to kick that member.")
    display = str(user) if user else uid
    await ctx.send(f"👢 **{display}** has been kicked.  Reason: {reason}")
    audit(f"kick  target={uid}  reason={reason!r}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(sid, f"👢 **Member Kicked**\nMember: {display} (`{uid}`)\nMod: {ctx.author}\nReason: {reason}")


@bot.command(name="ban")
@is_admin()
async def ban(ctx: commands.Context, user_arg, *, reason="No reason provided."):
    """Ban a member from the server. Accepts a mention or user ID. (Admin only)"""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    if uid == str(ctx.author.id):
        return await ctx.send("❌ You cannot ban yourself.")
    sid = get_server_id(ctx)
    if sid == "DM":
        return await ctx.send("❌ This command can only be used in a server.")
    try:
        server = await bot.fetch_server(sid)
        member = await server.fetch_member(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find member `{uid}` in this server.")
    # Fetch user independently so we have it cached before banning
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        user = None
    try:
        await (user or member.user).send(f"🔨 You have been banned.\nReason: {reason}")
    except Exception:
        pass
    try:
        await member.ban()
    except Exception:
        return await ctx.send("❌ I don't have permission to ban that member.")
    display = str(user) if user else uid
    await ctx.send(f"🔨 **{display}** has been banned.  Reason: {reason}")
    audit(f"ban  target={uid}  reason={reason!r}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(sid, f"🔨 **Member Banned**\nMember: {display} (`{uid}`)\nMod: {ctx.author}\nReason: {reason}")


@bot.command(name="unban")
@is_admin()
async def unban(ctx: commands.Context, user_id):
    """Unban a user by their ID or mention. (Admin only)"""
    uid = parse_user_id(user_id)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    sid = get_server_id(ctx)
    if sid == "DM":
        return await ctx.send("❌ This command can only be used in a server.")
    try:
        server = await bot.fetch_server(sid)
        await server.unban(uid)
    except Exception as e:
        return await ctx.send(f"❌ Could not unban `{uid}`: {e}")
    await ctx.send(f"✅ `{uid}` has been unbanned.")
    audit(f"unban  target={uid}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(sid, f"✅ **Member Unbanned**\nUser ID: `{uid}`\nMod: {ctx.author}")


# ==============================================================================
# --- Commands: Admin Configuration ---
# ==============================================================================

@bot.command(name="mute")
@is_admin()
async def mute(ctx: commands.Context, user_arg, *, reason="No reason provided."):
    """Apply the mute role to a member. Accepts a mention or user ID. (Admin only)"""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    sid = get_server_id(ctx)
    if sid == "DM":
        return await ctx.send("❌ This command can only be used in a server.")
    mute_role_id = cfg(sid).get("mute_role_id")
    if not mute_role_id:
        return await ctx.send("❌ No mute role configured. Use `set_mute_role` first.")
    try:
        server = await bot.fetch_server(sid)
        member = await server.fetch_member(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find member `{uid}` in this server.")
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        user = None
    current_roles = list(member.role_ids) if member.role_ids else []
    if mute_role_id in current_roles:
        return await ctx.send(f"❌ That member is already muted.")
    try:
        await member.edit(roles=cast(list, current_roles + [mute_role_id]))
    except Exception as e:
        return await ctx.send(f"❌ Could not mute that member: {e}")
    display = str(user) if user else uid
    await ctx.send(f"🔇 **{display}** has been muted.  Reason: {reason}")
    audit(f"mute  target={uid}  reason={reason!r}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(sid, f"🔇 **Member Muted**\nMember: {display} (`{uid}`)\nMod: {ctx.author}\nReason: {reason}")


@bot.command(name="unmute")
@is_admin()
async def unmute(ctx: commands.Context, user_arg):
    """Remove the mute role from a member. Accepts a mention or user ID. (Admin only)"""
    uid = parse_user_id(user_arg)
    if not uid:
        return await ctx.send("❌ Invalid user — provide a mention or user ID.")
    sid = get_server_id(ctx)
    if sid == "DM":
        return await ctx.send("❌ This command can only be used in a server.")
    mute_role_id = cfg(sid).get("mute_role_id")
    if not mute_role_id:
        return await ctx.send("❌ No mute role configured. Use `set_mute_role` first.")
    try:
        server = await bot.fetch_server(sid)
        member = await server.fetch_member(uid)
    except Exception:
        return await ctx.send(f"❌ Could not find member `{uid}` in this server.")
    try:
        user = await bot.fetch_user(uid)
    except Exception:
        user = None
    current_roles = list(member.role_ids) if member.role_ids else []
    if mute_role_id not in current_roles:
        return await ctx.send(f"❌ That member is not muted.")
    try:
        await member.edit(roles=cast(list, [r for r in current_roles if r != mute_role_id]))
    except Exception as e:
        return await ctx.send(f"❌ Could not unmute that member: {e}")
    display = str(user) if user else uid
    await ctx.send(f"🔊 **{display}** has been unmuted.")
    audit(f"unmute  target={uid}", server_id=sid, user_id=str(ctx.author.id))
    await post_to_log(sid, f"🔊 **Member Unmuted**\nMember: {display} (`{uid}`)\nMod: {ctx.author}")

@bot.command(name="set_log_channel")
@is_admin()
async def set_log_channel(ctx: commands.Context, channel_id):
    """Set the channel where bot events are logged. (Admin only)
    Usage: !set_log_channel <channel_id>"""
    gid = get_server_id(ctx)
    cfg(gid)["log_channel_id"] = channel_id
    save_json(CONFIG_FILE, server_cfg)
    await ctx.send(f"✅ Log channel set to `{channel_id}`.")
    audit(f"set_log_channel  channel={channel_id}", server_id=gid, user_id=str(ctx.author.id))


@bot.command(name="set_autorole")
@is_admin()
async def set_autorole(ctx: commands.Context, role_id):
    """Set the role automatically given to new members. (Admin only)
    Usage: !set_autorole <role_id>"""
    gid = get_server_id(ctx)
    cfg(gid)["autorole_id"] = role_id
    save_json(CONFIG_FILE, server_cfg)
    await ctx.send(f"✅ Auto-role set to `{role_id}`.")
    audit(f"set_autorole  role={role_id}", server_id=gid, user_id=str(ctx.author.id))


@bot.command(name="set_mute_role")
@is_admin()
async def set_mute_role(ctx: commands.Context, role_id):
    """Set the role used for muting. (Admin only)
    Usage: !set_mute_role <role_id>"""
    gid = get_server_id(ctx)
    cfg(gid)["mute_role_id"] = role_id
    save_json(CONFIG_FILE, server_cfg)
    await ctx.send(f"✅ Mute role set to `{role_id}`.")
    audit(f"set_mute_role  role={role_id}", server_id=gid, user_id=str(ctx.author.id))


@bot.command(name="status")
@is_admin()
async def status(ctx: commands.Context):
    """Show bot status and statistics. (Admin only)"""
    total_warnings     = sum(len(v) for v in warnings.values())
    servers_configured = len(server_cfg)
    await ctx.send(
        f"**📊 Bot Status**\n"
        f"Prefix: `{BOT_PREFIX}`\n"
        f"Total warnings on record: {total_warnings}\n"
        f"Servers with config: {servers_configured}\n"
        f"Admin IDs loaded: {len(ADMIN_USER_IDS)}\n"
        f"Data directory: `{DATA_DIR}/`"
    )


@bot.command(name="shutdown")
@is_admin()
async def shutdown(ctx: commands.Context):
    """Shut down the bot. (Admin only)"""
    gid = get_server_id(ctx)
    await ctx.send("🔴 Shutting down...")
    audit("admin_shutdown", server_id=gid, user_id=str(ctx.author.id))
    await bot.close()
    await asyncio.sleep(1)
    sys.exit(0)


# ==============================================================================
# --- Entry Point ---
# ==============================================================================

if __name__ == "__main__":
    setup_file_structure()
    load_all()

    if not BOT_TOKEN:
        print("❌ STOAT_BOT_TOKEN is not set.  Check your .env file.")
        sys.exit(1)

    if not ADMIN_USER_IDS:
        print("[WARN] STOAT_ADMIN_IDS is empty.  All admin commands will be inaccessible.")

    print(f"🚀 Starting bot with prefix '{BOT_PREFIX}' ...")
    try:
        bot.run(BOT_TOKEN, bot=True)
    except KeyboardInterrupt:
        print("\n⏸️ Bot interrupted by user.")