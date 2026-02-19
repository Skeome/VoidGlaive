import disnake
from disnake.ext import commands
import json
import datetime
import os
from typing import Optional, Dict, List
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# ==============================================================================
# --- Configuration ---
# ==============================================================================

BOT_TOKEN  = os.getenv("DISCORD_BOT_TOKEN")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

# Comma-separated Discord User IDs with elevated bot permissions
admin_ids_str  = os.getenv("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = [int(uid.strip()) for uid in admin_ids_str.split(",") if uid.strip()]

# Optional: comma-separated Guild IDs for instant slash-command registration during dev
test_guild_ids_str = os.getenv("TEST_GUILD_ID", "")
TEST_GUILD_IDS     = [int(gid.strip()) for gid in test_guild_ids_str.split(",") if gid.strip()]

# ==============================================================================
# --- File / Directory Paths ---
# Warnings and guild config are persisted to disk — both need to survive restarts
# to be meaningful. Everything else is stateless.
# ==============================================================================

DATA_DIR       = "discord"
AUDIT_LOG_PATH = os.path.join(DATA_DIR, "audit.log")
WARNINGS_FILE  = os.path.join(DATA_DIR, "warnings.json")  # warn / warnings / clear_warnings
CONFIG_FILE    = os.path.join(DATA_DIR, "config.json")    # log channel, autorole, mute role

# ==============================================================================
# --- In-memory state (loaded from disk at startup) ---
# ==============================================================================

# { "guild_id:user_id": [ {reason, mod_tag, mod_id, timestamp}, ... ] }
warnings: Dict[str, List[Dict]] = {}

# { "guild_id": { "log_channel_id": int, "autorole_id": int, "mute_role_id": int } }
guild_cfg: Dict[str, Dict] = {}


# ==============================================================================
# --- Helpers ---
# ==============================================================================

def setup_file_structure() -> None:
    """Creates the discord/ directory and persistent JSON files if they do not exist."""
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


def audit(action: str, guild_id: Optional[int] = None, user_id: Optional[int] = None) -> None:
    """Writes a timestamped entry to the audit log and stdout."""
    parts = [f"[{_now()}]", action]
    if guild_id:
        parts.append(f"guild:{guild_id}")
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
    global warnings, guild_cfg
    warnings  = load_json(WARNINGS_FILE)
    guild_cfg = load_json(CONFIG_FILE)


def warning_key(guild_id: int, user_id: int) -> str:
    return f"{guild_id}:{user_id}"


def cfg(guild_id: int) -> Dict:
    """Returns the config dict for a guild, creating it if absent."""
    return guild_cfg.setdefault(str(guild_id), {})


def get_log_channel(guild: disnake.Guild) -> Optional[disnake.TextChannel]:
    cid = cfg(guild.id).get("log_channel_id")
    if not cid:
        return None
    ch = guild.get_channel(cid)
    return ch if isinstance(ch, disnake.TextChannel) else None


async def send_log(guild: disnake.Guild, embed: disnake.Embed) -> None:
    """Posts a log embed to the guild's configured log channel."""
    ch = get_log_channel(guild)
    if ch:
        try:
            await ch.send(embed=embed)
        except disnake.Forbidden:
            pass


async def respond(
    inter: disnake.ApplicationCommandInteraction,
    content: str,
    *,
    color: disnake.Color = disnake.Color.blurple(),
    title: Optional[str] = None,
) -> None:
    embed = disnake.Embed(description=content, color=color)
    if title:
        embed.title = title
    await inter.edit_original_response(embed=embed)


async def respond_error(inter: disnake.ApplicationCommandInteraction, content: str) -> None:
    await respond(inter, f"❌  {content}", color=disnake.Color.red())


async def guild_guard(inter: disnake.ApplicationCommandInteraction) -> Optional[disnake.Guild]:
    """Returns inter.guild if present, otherwise sends an error and returns None."""
    if inter.guild is None:
        await respond_error(inter, "This command can only be used in a server.")
        return None
    return inter.guild


async def channel_guard(inter: disnake.ApplicationCommandInteraction) -> Optional[disnake.TextChannel]:
    """Returns inter.channel as TextChannel if possible, otherwise sends an error and returns None."""
    if not isinstance(inter.channel, disnake.TextChannel):
        await respond_error(inter, "This command can only be used in a text channel.")
        return None
    return inter.channel


# ==============================================================================
# --- Bot Setup ---
# ==============================================================================

intents = disnake.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=BOT_PREFIX,
    intents=intents,
    test_guilds=TEST_GUILD_IDS or None,
    help_command=None,
)


# ==============================================================================
# --- Events ---
# ==============================================================================

@bot.event
async def on_ready() -> None:
    audit(f"Bot online  tag={bot.user}  id={bot.user.id}")
    print(f"\n✅  Logged in as {bot.user}  (ID: {bot.user.id})")
    print(f"   Guilds : {len(bot.guilds)}")
    print(f"   Prefix : {BOT_PREFIX}\n")
    await bot.change_presence(
        activity=disnake.Activity(type=disnake.ActivityType.watching, name=f"{BOT_PREFIX}help")
    )


@bot.event
async def on_member_join(member: disnake.Member) -> None:
    audit("member_join", guild_id=member.guild.id, user_id=member.id)

    # Auto-role
    role_id = cfg(member.guild.id).get("autorole_id")
    if role_id:
        role = member.guild.get_role(role_id)
        if role:
            try:
                await member.add_roles(role, reason="Auto-role on join")
            except disnake.Forbidden:
                print(f"[WARN] Cannot assign auto-role in {member.guild.name}")

    embed = disnake.Embed(
        title="📥  Member Joined",
        description=f"{member.mention}  (`{member}`)",
        color=disnake.Color.green(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
    embed.set_footer(text=f"ID: {member.id}")
    await send_log(member.guild, embed)


@bot.event
async def on_member_remove(member: disnake.Member) -> None:
    audit("member_leave", guild_id=member.guild.id, user_id=member.id)
    embed = disnake.Embed(
        title="📤  Member Left",
        description=f"{member.mention}  (`{member}`)",
        color=disnake.Color.orange(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    embed.set_footer(text=f"ID: {member.id}")
    await send_log(member.guild, embed)


@bot.event
async def on_message_delete(message: disnake.Message) -> None:
    if message.author.bot or not message.guild:
        return
    embed = disnake.Embed(
        title="🗑️  Message Deleted",
        description=f"In {getattr(message.channel, 'mention', str(message.channel))} by {message.author.mention}",
        color=disnake.Color.red(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    if message.content:
        embed.add_field(name="Content", value=message.content[:1024], inline=False)
    embed.set_footer(text=f"Author ID: {message.author.id}")
    await send_log(message.guild, embed)


@bot.event
async def on_message_edit(before: disnake.Message, after: disnake.Message) -> None:
    if before.author.bot or not before.guild or before.content == after.content:
        return
    embed = disnake.Embed(
        title="✏️  Message Edited",
        description=f"In {getattr(before.channel, 'mention', str(before.channel))} by {before.author.mention}",
        color=disnake.Color.yellow(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    embed.add_field(name="Before", value=before.content[:512] or "*(empty)*", inline=False)
    embed.add_field(name="After",  value=after.content[:512]  or "*(empty)*", inline=False)
    embed.set_footer(text=f"Author ID: {before.author.id}")
    await send_log(before.guild, embed)


@bot.event
async def on_command_error(ctx: commands.Context, error: Exception) -> None:
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳  Cooldown — retry in {error.retry_after:.1f}s.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌  You don't have permission to use that command.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"⚠️  Bad argument: {error}")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"[ERROR] command={ctx.command}  {error}")
        await ctx.send("⚠️  An unexpected error occurred.")


# ==============================================================================
# --- Slash Commands: Information ---
# ==============================================================================

@bot.slash_command(name="help", description="Lists all available commands.")
async def help_cmd(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    embed = disnake.Embed(
        title="📖  Command Reference",
        color=disnake.Color.blurple(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    sections = {
        "ℹ️  Information": [
            "`/help`  — This message",
            "`/ping`  — Bot latency",
            "`/botinfo`  — Bot statistics",
            "`/serverinfo`  — Server details",
            "`/userinfo [member]`  — User details",
            "`/avatar [member]`  — Display avatar",
            "`/roleinfo <role>`  — Role details",
        ],
        "⚠️  Warnings": [
            "`/warn <member> <reason>`  — Warn a member",
            "`/warnings <member>`  — View a member's warnings",
            "`/clear_warnings <member>`  — Remove all warnings",
        ],
        "🔨  Moderation": [
            "`/kick <member> [reason]`  — Kick a member",
            "`/ban <member> [reason]`  — Ban a member",
            "`/unban <user_id> [reason]`  — Unban a user",
            "`/mute <member> [reason]`  — Mute a member",
            "`/unmute <member>`  — Unmute a member",
            "`/purge <amount>`  — Bulk-delete messages (max 100)",
            "`/slowmode <seconds>`  — Set channel slowmode",
            "`/lock`  — Lock the current channel",
            "`/unlock`  — Unlock the current channel",
        ],
        "⚙️  Admin Config": [
            "`/set_log_channel <channel>`  — Set the log channel",
            "`/set_autorole <role>`  — Set the auto-role on join",
            "`/set_mute_role <role>`  — Set the muted role",
        ],
    }
    for section, lines in sections.items():
        embed.add_field(name=section, value="\n".join(lines), inline=False)
    embed.set_footer(text=f"Prefix: {BOT_PREFIX}")
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="ping", description="Check the bot's latency.")
async def ping(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    await respond(inter, f"🏓  Pong!  Latency: **{round(bot.latency * 1000)} ms**")


@bot.slash_command(name="botinfo", description="Display statistics about the bot.")
async def botinfo(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    embed = disnake.Embed(title="🤖  Bot Info", color=disnake.Color.blurple(), timestamp=datetime.datetime.now(datetime.UTC))
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Guilds",  value=str(len(bot.guilds)),            inline=True)
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)} ms", inline=True)
    embed.add_field(name="Prefix",  value=BOT_PREFIX,                      inline=True)
    embed.set_footer(text=f"ID: {bot.user.id}")
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="serverinfo", description="Display information about this server.")
async def serverinfo(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    g = inter.guild
    if g is None:
        await respond_error(inter, "This command can only be used in a server.")
        return
    embed = disnake.Embed(title=f"🏠  {g.name}", color=disnake.Color.blurple(), timestamp=datetime.datetime.now(datetime.UTC))
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Owner",    value=str(g.owner),          inline=True)
    embed.add_field(name="Members",  value=str(g.member_count),   inline=True)
    embed.add_field(name="Channels", value=str(len(g.channels)),  inline=True)
    embed.add_field(name="Roles",    value=str(len(g.roles)),     inline=True)
    embed.add_field(name="Boosts",   value=str(g.premium_subscription_count), inline=True)
    embed.add_field(name="Created",  value=g.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.set_footer(text=f"ID: {g.id}")
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="userinfo", description="Display information about a member.")
async def userinfo(
    inter: disnake.ApplicationCommandInteraction,
    member: Optional[disnake.Member] = commands.Param(default=None, description="Member to look up (defaults to you)"),
) -> None:
    await inter.response.defer()
    member = member or (inter.author if isinstance(inter.author, disnake.Member) else None)
    if not member:
        await respond_error(inter, "Could not resolve member. Use this command in a server.")
        return
    embed = disnake.Embed(
        title=f"👤  {member}",
        color=member.color if member.color != disnake.Color.default() else disnake.Color.blurple(),
        timestamp=datetime.datetime.now(datetime.UTC),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID",       value=str(member.id),        inline=True)
    embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
    embed.add_field(name="Bot",      value=str(member.bot),       inline=True)
    embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Joined Server",   value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "?", inline=True)
    roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
    embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles) if roles else "None", inline=False)
    wcount = len(warnings.get(warning_key(inter.guild.id, member.id), [])) if inter.guild else 0
    embed.add_field(name="Warnings", value=str(wcount), inline=True)
    embed.set_footer(text=f"ID: {member.id}")
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="avatar", description="Display a member's avatar.")
async def avatar(
    inter: disnake.ApplicationCommandInteraction,
    member: Optional[disnake.Member] = commands.Param(default=None, description="Member (defaults to you)"),
) -> None:
    await inter.response.defer()
    target = member or inter.author
    embed = disnake.Embed(title=f"🖼️  {target.display_name}'s Avatar", color=disnake.Color.blurple())
    embed.set_image(url=target.display_avatar.url)
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="roleinfo", description="Display information about a role.")
async def roleinfo(inter: disnake.ApplicationCommandInteraction, role: disnake.Role) -> None:
    await inter.response.defer()
    embed = disnake.Embed(title=f"🎭  Role: {role.name}", color=role.color, timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="ID",          value=str(role.id),                        inline=True)
    embed.add_field(name="Members",     value=str(len(role.members)),               inline=True)
    embed.add_field(name="Mentionable", value=str(role.mentionable),                inline=True)
    embed.add_field(name="Hoisted",     value=str(role.hoist),                      inline=True)
    embed.add_field(name="Position",    value=str(role.position),                   inline=True)
    embed.add_field(name="Created",     value=role.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.set_footer(text=f"ID: {role.id}")
    await inter.edit_original_response(embed=embed)


# ==============================================================================
# --- Slash Commands: Warnings (persisted to warnings.json) ---
# ==============================================================================

@bot.slash_command(name="warn", description="Issue a warning to a member.")
@commands.has_permissions(manage_messages=True)
async def warn(inter: disnake.ApplicationCommandInteraction, member: disnake.Member, reason: str) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    if member.bot:
        await respond_error(inter, "You cannot warn a bot.")
        return
    key = warning_key(guild.id, member.id)
    warnings.setdefault(key, []).append({
        "reason":    reason,
        "mod_id":    inter.author.id,
        "mod_tag":   str(inter.author),
        "timestamp": _now(),
    })
    save_json(WARNINGS_FILE, warnings)
    total = len(warnings[key])

    try:
        await member.send(
            f"⚠️  You have been warned in **{guild.name}**.\n"
            f"Reason: {reason}\nTotal warnings: {total}"
        )
    except disnake.Forbidden:
        pass

    await respond(inter, f"⚠️  {member.mention} warned.  Reason: {reason}  (Total: {total})")
    audit(f"warn  target={member.id}  reason={reason!r}", guild_id=guild.id, user_id=inter.author.id)

    embed = disnake.Embed(title="⚠️  Member Warned", color=disnake.Color.yellow(), timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="Member", value=str(member),       inline=True)
    embed.add_field(name="Mod",    value=str(inter.author), inline=True)
    embed.add_field(name="Reason", value=reason,            inline=False)
    embed.add_field(name="Total",  value=str(total),        inline=True)
    await send_log(guild, embed)


@bot.slash_command(name="warnings", description="View warnings for a member.")
@commands.has_permissions(manage_messages=True)
async def view_warnings(inter: disnake.ApplicationCommandInteraction, member: disnake.Member) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    wlist = warnings.get(warning_key(guild.id, member.id), [])
    if not wlist:
        await respond(inter, f"{member.mention} has no warnings.")
        return
    embed = disnake.Embed(title=f"⚠️  Warnings for {member}  ({len(wlist)})", color=disnake.Color.orange())
    for i, w in enumerate(wlist, 1):
        embed.add_field(
            name=f"#{i}  —  {w['timestamp']}",
            value=f"Reason: {w['reason']}\nMod: {w['mod_tag']}",
            inline=False,
        )
    await inter.edit_original_response(embed=embed)


@bot.slash_command(name="clear_warnings", description="Remove all warnings for a member.")
@commands.has_permissions(administrator=True)
async def clear_warnings(inter: disnake.ApplicationCommandInteraction, member: disnake.Member) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    key = warning_key(guild.id, member.id)
    if key in warnings:
        del warnings[key]
        save_json(WARNINGS_FILE, warnings)
        await respond(inter, f"✅  All warnings cleared for {member.mention}.")
    else:
        await respond(inter, f"{member.mention} has no warnings to clear.")
    audit(f"clear_warnings  target={member.id}", guild_id=guild.id, user_id=inter.author.id)


# ==============================================================================
# --- Slash Commands: Moderation ---
# ==============================================================================

@bot.slash_command(name="kick", description="Kick a member from the server.")
@commands.has_permissions(kick_members=True)
async def kick(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "No reason provided.",
) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    if member == inter.author:
        await respond_error(inter, "You cannot kick yourself.")
        return
    try:
        await member.send(f"👢  You have been kicked from **{guild.name}**.\nReason: {reason}")
    except disnake.Forbidden:
        pass
    try:
        await member.kick(reason=reason)
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to kick that member.")
        return
    await respond(inter, f"👢  **{member}** has been kicked.  Reason: {reason}")
    audit(f"kick  target={member.id}  reason={reason!r}", guild_id=guild.id, user_id=inter.author.id)

    embed = disnake.Embed(title="👢  Member Kicked", color=disnake.Color.red(), timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="Member", value=str(member),       inline=True)
    embed.add_field(name="Mod",    value=str(inter.author), inline=True)
    embed.add_field(name="Reason", value=reason,            inline=False)
    await send_log(guild, embed)


@bot.slash_command(name="ban", description="Ban a member from the server.")
@commands.has_permissions(ban_members=True)
async def ban(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "No reason provided.",
    delete_message_days: int = commands.Param(default=0, ge=0, le=7, description="Days of messages to delete (0–7)"),
) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    if member == inter.author:
        await respond_error(inter, "You cannot ban yourself.")
        return
    try:
        await member.send(f"🔨  You have been banned from **{guild.name}**.\nReason: {reason}")
    except disnake.Forbidden:
        pass
    # Clamp to Literal[0..7] so Pylance is satisfied
    safe_days = max(0, min(7, delete_message_days))
    try:
        await member.ban(reason=reason, delete_message_days=safe_days)  # type: ignore[arg-type]
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to ban that member.")
        return
    await respond(inter, f"🔨  **{member}** has been banned.  Reason: {reason}")
    audit(f"ban  target={member.id}  reason={reason!r}", guild_id=guild.id, user_id=inter.author.id)

    embed = disnake.Embed(title="🔨  Member Banned", color=disnake.Color.dark_red(), timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="Member", value=str(member),       inline=True)
    embed.add_field(name="Mod",    value=str(inter.author), inline=True)
    embed.add_field(name="Reason", value=reason,            inline=False)
    await send_log(guild, embed)


@bot.slash_command(name="unban", description="Unban a user by their ID.")
@commands.has_permissions(ban_members=True)
async def unban(inter: disnake.ApplicationCommandInteraction, user_id: str, reason: str = "No reason provided.") -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    try:
        uid = int(user_id)
    except ValueError:
        await respond_error(inter, "Invalid user ID — must be a number.")
        return
    try:
        await guild.unban(disnake.Object(id=uid), reason=reason)
        await respond(inter, f"✅  User `{uid}` has been unbanned.")
    except disnake.NotFound:
        await respond_error(inter, "That user is not currently banned.")
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to unban users.")
    audit(f"unban  target={uid}", guild_id=guild.id, user_id=inter.author.id)


@bot.slash_command(name="mute", description="Mute a member (requires a muted role to be configured).")
@commands.has_permissions(manage_roles=True)
async def mute(
    inter: disnake.ApplicationCommandInteraction,
    member: disnake.Member,
    reason: str = "No reason provided.",
) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    role_id = cfg(guild.id).get("mute_role_id")
    if not role_id:
        await respond_error(inter, "No muted role configured.  Use `/set_mute_role` first.")
        return
    role = guild.get_role(role_id)
    if not role:
        await respond_error(inter, "The configured muted role no longer exists.")
        return
    if role in member.roles:
        await respond_error(inter, f"{member.mention} is already muted.")
        return
    try:
        await member.add_roles(role, reason=reason)
        await respond(inter, f"🔇  {member.mention} has been muted.  Reason: {reason}")
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to manage that member's roles.")
        return
    audit(f"mute  target={member.id}  reason={reason!r}", guild_id=guild.id, user_id=inter.author.id)

    embed = disnake.Embed(title="🔇  Member Muted", color=disnake.Color.greyple(), timestamp=datetime.datetime.now(datetime.UTC))
    embed.add_field(name="Member", value=str(member),       inline=True)
    embed.add_field(name="Mod",    value=str(inter.author), inline=True)
    embed.add_field(name="Reason", value=reason,            inline=False)
    await send_log(guild, embed)


@bot.slash_command(name="unmute", description="Unmute a member.")
@commands.has_permissions(manage_roles=True)
async def unmute(inter: disnake.ApplicationCommandInteraction, member: disnake.Member) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    role_id = cfg(guild.id).get("mute_role_id")
    if not role_id:
        await respond_error(inter, "No muted role configured.")
        return
    role = guild.get_role(role_id)
    if not role or role not in member.roles:
        await respond_error(inter, f"{member.mention} is not currently muted.")
        return
    try:
        await member.remove_roles(role, reason="Unmuted")
        await respond(inter, f"🔊  {member.mention} has been unmuted.")
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to manage that member's roles.")
    audit(f"unmute  target={member.id}", guild_id=guild.id, user_id=inter.author.id)


@bot.slash_command(name="purge", description="Bulk-delete messages from the current channel (max 100).")
@commands.has_permissions(manage_messages=True)
async def purge(
    inter: disnake.ApplicationCommandInteraction,
    amount: int = commands.Param(ge=1, le=100, description="Number of messages to delete"),
) -> None:
    await inter.response.defer(ephemeral=True)
    guild = await guild_guard(inter)
    if guild is None:
        return
    channel = await channel_guard(inter)
    if channel is None:
        return
    deleted = await channel.purge(limit=amount)
    await inter.edit_original_response(content=f"🗑️  Deleted {len(deleted)} message(s).")
    audit(f"purge  count={len(deleted)}", guild_id=guild.id, user_id=inter.author.id)


@bot.slash_command(name="slowmode", description="Set slowmode for the current channel.")
@commands.has_permissions(manage_channels=True)
async def slowmode(
    inter: disnake.ApplicationCommandInteraction,
    seconds: int = commands.Param(ge=0, le=21600, description="Slowmode delay in seconds (0 to disable)"),
) -> None:
    await inter.response.defer()
    guild = await guild_guard(inter)
    if guild is None:
        return
    channel = await channel_guard(inter)
    if channel is None:
        return
    try:
        await channel.edit(slowmode_delay=seconds)
        msg = f"✅  Slowmode disabled in {channel.mention}." if seconds == 0 \
              else f"✅  Slowmode set to **{seconds}s** in {channel.mention}."
        await respond(inter, msg)
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to edit that channel.")
    audit(f"slowmode  seconds={seconds}", guild_id=guild.id, user_id=inter.author.id)


@bot.slash_command(name="lock", description="Prevent members from sending messages in this channel.")
@commands.has_permissions(manage_channels=True)
async def lock(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    if inter.guild is None or not isinstance(inter.channel, disnake.TextChannel):
        await respond_error(inter, "This command can only be used in a text channel.")
        return
    overwrite = inter.channel.overwrites_for(inter.guild.default_role)
    overwrite.send_messages = False
    try:
        await inter.channel.set_permissions(inter.guild.default_role, overwrite=overwrite)
        await respond(inter, f"🔒  {inter.channel.mention} is now locked.")
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to manage that channel.")
    audit("lock_channel", guild_id=inter.guild.id, user_id=inter.author.id)


@bot.slash_command(name="unlock", description="Allow members to send messages in this channel again.")
@commands.has_permissions(manage_channels=True)
async def unlock(inter: disnake.ApplicationCommandInteraction) -> None:
    await inter.response.defer()
    if inter.guild is None or not isinstance(inter.channel, disnake.TextChannel):
        await respond_error(inter, "This command can only be used in a text channel.")
        return
    overwrite = inter.channel.overwrites_for(inter.guild.default_role)
    overwrite.send_messages = None  # reset to inherit
    try:
        await inter.channel.set_permissions(inter.guild.default_role, overwrite=overwrite)
        await respond(inter, f"🔓  {inter.channel.mention} is now unlocked.")
    except disnake.Forbidden:
        await respond_error(inter, "I don't have permission to manage that channel.")
    audit("unlock_channel", guild_id=inter.guild.id, user_id=inter.author.id)


# ==============================================================================
# --- Slash Commands: Admin Configuration (persisted to config.json) ---
# ==============================================================================

@bot.slash_command(name="set_log_channel", description="[ADMIN] Set the channel where bot events are logged.")
@commands.has_permissions(administrator=True)
async def set_log_channel(inter: disnake.ApplicationCommandInteraction, channel: disnake.TextChannel) -> None:
    await inter.response.defer()
    if inter.guild is None:
        await respond_error(inter, "This command can only be used in a server.")
        return
    cfg(inter.guild.id)["log_channel_id"] = channel.id
    save_json(CONFIG_FILE, guild_cfg)
    await respond(inter, f"✅  Log channel set to {channel.mention}.")
    audit(f"set_log_channel  channel={channel.id}", guild_id=inter.guild.id, user_id=inter.author.id)


@bot.slash_command(name="set_autorole", description="[ADMIN] Set the role automatically given to new members.")
@commands.has_permissions(administrator=True)
async def set_autorole(inter: disnake.ApplicationCommandInteraction, role: disnake.Role) -> None:
    await inter.response.defer()
    if inter.guild is None:
        await respond_error(inter, "This command can only be used in a server.")
        return
    cfg(inter.guild.id)["autorole_id"] = role.id
    save_json(CONFIG_FILE, guild_cfg)
    await respond(inter, f"✅  Auto-role set to {role.mention}.")
    audit(f"set_autorole  role={role.id}", guild_id=inter.guild.id, user_id=inter.author.id)


@bot.slash_command(name="set_mute_role", description="[ADMIN] Set the role used by /mute and /unmute.")
@commands.has_permissions(administrator=True)
async def set_mute_role(inter: disnake.ApplicationCommandInteraction, role: disnake.Role) -> None:
    await inter.response.defer()
    if inter.guild is None:
        await respond_error(inter, "This command can only be used in a server.")
        return
    cfg(inter.guild.id)["mute_role_id"] = role.id
    save_json(CONFIG_FILE, guild_cfg)
    await respond(inter, f"✅  Muted role set to {role.mention}.")
    audit(f"set_mute_role  role={role.id}", guild_id=inter.guild.id, user_id=inter.author.id)


# ==============================================================================
# --- Entry Point ---
# ==============================================================================

if __name__ == "__main__":
    setup_file_structure()
    load_all()

    if not BOT_TOKEN:
        raise ValueError("DISCORD_BOT_TOKEN is not set.  Check your .env file.")
    if not ADMIN_USER_IDS:
        print("[WARN] ADMIN_USER_IDS is empty.  Bot-level admin overrides will not be active.")

    print(f"Starting bot with prefix '{BOT_PREFIX}' ...")
    bot.run(BOT_TOKEN)