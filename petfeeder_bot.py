#!/usr/bin/env python3
"""Telegram bot for controlling a Tuya-based automatic pet feeder.

Provides commands:
  - /feed: dispenses a configured number of food portions
  - /status: queries and displays the current device state
  - /addtimer: schedules automatic feeding
  - /timers: lists all scheduled feeding times
  - /deletetimer: removes a scheduled feeding time
"""

import configparser
import json
import logging
import sys
import zoneinfo
from datetime import time
from pathlib import Path
from typing import Final

import tinytuya
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    JobQueue,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_PATH: Final[str] = str(Path(__file__).resolve().parent / "petfeeder.conf")
TIMERS_PATH: Final[str] = str(Path(__file__).resolve().parent / "timers.json")


def load_config(path: str = CONFIG_PATH) -> configparser.ConfigParser:
    """Read and validate the configuration file.

    Args:
        path: Absolute or relative path to the .conf file.

    Returns:
        Parsed ConfigParser instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        KeyError: If a required section or option is missing.
    """
    config = configparser.ConfigParser()

    if not Path(path).is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")

    config.read(path, encoding="utf-8")

    required_sections = {
        "telegram": ["bot_token", "allowed_user_ids"],
        "device": [
            "device_id",
            "ip_address",
            "local_key",
            "version",
            "feed_dp",
            "portions",
        ],
    }

    for section, keys in required_sections.items():
        if not config.has_section(section):
            raise KeyError(f"Missing required config section: [{section}]")
        for key in keys:
            if not config.get(section, key, fallback=""):
                raise KeyError(f"Missing required config option: [{section}] {key}")

    return config


CONFIG: Final[configparser.ConfigParser] = load_config()

# Telegram settings
BOT_TOKEN: Final[str] = CONFIG.get("telegram", "bot_token")
ALLOWED_USER_IDS: set[int] = set(
    int(uid.strip())
    for uid in CONFIG.get("telegram", "allowed_user_ids").split(",")
    if uid.strip()
)

# Device settings
DEVICE_ID: Final[str] = CONFIG.get("device", "device_id")
IP_ADDRESS: Final[str] = CONFIG.get("device", "ip_address")
LOCAL_KEY: Final[str] = CONFIG.get("device", "local_key")
DEVICE_VERSION: Final[float] = CONFIG.getfloat("device", "version")
FEED_DP: Final[str] = CONFIG.get("device", "feed_dp")
PORTIONS: Final[int] = CONFIG.getint("device", "portions")

# Timezone
TIMEZONE: Final[zoneinfo.ZoneInfo] = zoneinfo.ZoneInfo(
    CONFIG.get("general", "timezone", fallback="UTC")
)

# Logging settings
LOG_LEVEL: Final[str] = CONFIG.get("logging", "level", fallback="INFO").upper()
LOG_FILE: Final[str] = CONFIG.get("logging", "file", fallback="")

# Timer storage
TIMERS: dict[str, dict] = {}  # Format: {"HH:MM": {"portions": int, "job": Job}}

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------


def setup_logging() -> None:
    """Configure the root logger based on settings from the config file."""
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if LOG_FILE:
        handlers.append(logging.FileHandler(LOG_FILE, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
    )


setup_logging()
logger: Final[logging.Logger] = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Device helpers
# ---------------------------------------------------------------------------


def get_device() -> tinytuya.OutletDevice:
    """Create and return a configured Tuya device instance.

    Returns:
        A tinytuya OutletDevice ready for communication.
    """
    device = tinytuya.OutletDevice(DEVICE_ID, IP_ADDRESS, LOCAL_KEY)
    device.set_version(DEVICE_VERSION)
    return device


def query_status() -> dict:
    """Query the device and return its current status dictionary.

    Returns:
        Raw status dict from the device, or a dict with an 'Error' key.
    """
    device = get_device()
    status = device.status()
    logger.info("Device status queried: %s", status)
    return status


def trigger_feed(portions: int = PORTIONS) -> dict:
    """Send a feed command to the device.

    Args:
        portions: Number of food portions to dispense.

    Returns:
        Raw response dict from the device.
    """
    device = get_device()
    payload = device.generate_payload(tinytuya.CONTROL, {FEED_DP: portions})
    result = device.send(payload)
    logger.info("Feed command sent (%d portion(s)): %s", portions, result)
    return result


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def is_authorized(user_id: int) -> bool:
    """Check whether a Telegram user is allowed to use the bot.

    Args:
        user_id: Telegram user ID to verify.

    Returns:
        True if the user is in the allowed list.
    """
    return user_id in ALLOWED_USER_IDS


def save_allowed_user_ids() -> None:
    """Persist the current ALLOWED_USER_IDS set back to the config file."""
    CONFIG.set(
        "telegram",
        "allowed_user_ids",
        ", ".join(str(uid) for uid in sorted(ALLOWED_USER_IDS)),
    )
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        CONFIG.write(f)
    logger.info("allowed_user_ids saved to config: %s", ALLOWED_USER_IDS)


# ---------------------------------------------------------------------------
# Timer management
# ---------------------------------------------------------------------------


def load_timers() -> dict[str, dict]:
    """Load timer configuration from JSON file.

    Returns:
        Dictionary with timer data (without job objects).
    """
    if not Path(TIMERS_PATH).is_file():
        return {}

    try:
        with open(TIMERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info("Loaded timers from file: %s", data)
            return data
    except Exception as e:
        logger.error("Failed to load timers: %s", e)
        return {}


def save_timers() -> None:
    """Persist timer configuration to JSON file (without job objects)."""
    data = {
        timer_key: {"portions": info["portions"]} for timer_key, info in TIMERS.items()
    }
    try:
        with open(TIMERS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("Saved timers to file: %s", data)
    except Exception as e:
        logger.error("Failed to save timers: %s", e)


async def timer_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute scheduled feeding."""
    portions = context.job.data.get("portions", PORTIONS)
    timer_key = context.job.data.get("timer_key", "unknown")

    logger.info("Timer %s triggered, feeding %d portions", timer_key, portions)

    try:
        trigger_feed(portions)
        logger.info("Scheduled feeding completed for timer %s", timer_key)
    except Exception as e:
        logger.error(
            "Failed to execute scheduled feeding for timer %s: %s", timer_key, e
        )


# ---------------------------------------------------------------------------
# Timer initialization
# ---------------------------------------------------------------------------


def schedule_timer(job_queue: JobQueue, timer_key: str, portions: int) -> None:
    """Schedule a daily feeding timer.

    Args:
        job_queue: Telegram job queue instance.
        timer_key: Time string in HH:MM format.
        portions: Number of portions to feed.
    """
    try:
        hour, minute = map(int, timer_key.split(":"))
        feed_time = time(hour=hour, minute=minute, tzinfo=TIMEZONE)

        job = job_queue.run_daily(
            timer_callback,
            time=feed_time,
            data={"timer_key": timer_key, "portions": portions},
            name=f"timer_{timer_key}",
        )

        TIMERS[timer_key] = {"portions": portions, "job": job}
        logger.info("Scheduled timer %s for %d portions", timer_key, portions)
    except Exception as e:
        logger.error("Failed to schedule timer %s: %s", timer_key, e)
        raise


def init_timers(job_queue: JobQueue) -> None:
    """Load and schedule all saved timers on bot startup.

    Args:
        job_queue: Telegram job queue instance.
    """
    saved_timers = load_timers()
    for timer_key, data in saved_timers.items():
        try:
            schedule_timer(job_queue, timer_key, data["portions"])
        except Exception as e:
            logger.error("Failed to restore timer %s: %s", timer_key, e)


# ---------------------------------------------------------------------------
# Bot handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command — greet the user."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized access attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    logger.info("User %s (%d) started the bot", user.full_name, user.id)
    await update.message.reply_text(
        f"👋 Hello, {user.first_name}!\n\n"
        f"Pet Feeder Bot is ready. Use /help to see available commands."
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command — show available commands."""
    user = update.effective_user
    if user is None:
        return

    help_text = (
        "📖 *Available Commands:*\n\n"
        "/myid — Get your Telegram user ID\n"
        "/help — Show this help message\n"
    )

    if user and is_authorized(user.id):
        help_text += (
            "\n*Feeder Control:*\n"
            f"/feed — Feed the pet ({PORTIONS} portions)\n"
            "/status — Check device status\n"
            "\n*Timer Management:*\n"
            "/addtimer HH:MM portions — Schedule feeding\n"
            "/timers — List all scheduled feedings\n"
            "/deletetimer HH:MM — Remove scheduled feeding\n"
            "\n*User Management:*\n"
            "/adduser <user\\_id> — Add user to allowed list\n"
        )
    else:
        help_text += "\n_Contact an authorized user to get access._"

    await update.message.reply_text(help_text, parse_mode="Markdown")


async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /myid command — tell the user their Telegram ID (no auth required)."""
    user = update.effective_user
    if user is None:
        return

    logger.info("User %s (%d) requested their ID", user.full_name, user.id)
    await update.message.reply_text(
        f"🆔 Your Telegram user ID: `{user.id}`", parse_mode="Markdown"
    )


async def cmd_adduser(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /adduser <id> command — add a user ID to the allowed list (auth required)."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /adduser attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/adduser <user_id>`", parse_mode="Markdown"
        )
        return

    try:
        new_uid = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid user ID. Please provide a numeric ID."
        )
        return

    if new_uid in ALLOWED_USER_IDS:
        await update.message.reply_text(
            f"ℹ️ User `{new_uid}` is already in the allowed list.", parse_mode="Markdown"
        )
        return

    ALLOWED_USER_IDS.add(new_uid)
    save_allowed_user_ids()

    logger.info(
        "User %s (%d) added user %d to allowed list", user.full_name, user.id, new_uid
    )
    await update.message.reply_text(
        f"✅ User `{new_uid}` has been added to the allowed list.",
        parse_mode="Markdown",
    )


async def cmd_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /feed command — feed the pet."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /feed attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    logger.info("User %s (%d) requested feeding", user.full_name, user.id)

    try:
        result = trigger_feed()
        error = result.get("Error") if isinstance(result, dict) else None

        if error:
            text = f"⚠️ Feed command sent but device returned an error:\n`{error}`"
            logger.error("Feed error: %s", error)
        else:
            text = f"✅ Fed the pet! Dispensed {PORTIONS} portion(s)."
    except Exception:
        logger.exception("Failed to send feed command")
        text = "❌ Failed to communicate with the feeder. Check the device connection."

    await update.message.reply_text(text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command — query device status."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /status attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    logger.info("User %s (%d) requested status", user.full_name, user.id)

    try:
        status = query_status()
        error = status.get("Error") if isinstance(status, dict) else None

        if error:
            text = f"⚠️ Device returned an error:\n`{error}`"
            logger.error("Status error: %s", error)
        else:
            dps = status.get("dps", {})
            lines = [
                f"  `{dp}`: `{value}`"
                for dp, value in sorted(dps.items(), key=lambda x: str(x[0]))
            ]
            dps_text = "\n".join(lines) if lines else "  (no data points)"
            text = f"📊 *Device Status*\n\n{dps_text}"
    except Exception:
        logger.exception("Failed to query device status")
        text = "❌ Failed to communicate with the feeder. Check the device connection."

    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_addtimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /addtimer HH:MM portions command — schedule a feeding timer."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /addtimer attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: `/addtimer HH:MM portions`\nExample: `/addtimer 08:00 2`",
            parse_mode="Markdown",
        )
        return

    timer_key = context.args[0]

    # Validate time format
    try:
        hour, minute = map(int, timer_key.split(":"))
        if not (0 <= hour < 24 and 0 <= minute < 60):
            raise ValueError("Invalid time range")
        timer_key = f"{hour:02d}:{minute:02d}"  # Normalize format
    except (ValueError, AttributeError):
        await update.message.reply_text(
            "⚠️ Invalid time format. Use HH:MM (e.g., 08:00)"
        )
        return

    # Validate portions
    try:
        portions = int(context.args[1])
        if portions <= 0:
            raise ValueError("Portions must be positive")
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid portions number. Must be a positive integer."
        )
        return

    # Check if timer already exists
    if timer_key in TIMERS:
        await update.message.reply_text(
            f"ℹ️ Timer for `{timer_key}` already exists. Delete it first with /deletetimer",
            parse_mode="Markdown",
        )
        return

    # Schedule the timer
    try:
        schedule_timer(context.application.job_queue, timer_key, portions)
        save_timers()

        logger.info(
            "User %s (%d) added timer %s with %d portions",
            user.full_name,
            user.id,
            timer_key,
            portions,
        )
        await update.message.reply_text(
            f"✅ Timer added: `{timer_key}` — {portions} portion(s)",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.exception("Failed to add timer %s", timer_key)
        await update.message.reply_text(f"❌ Failed to add timer: {e}")


async def cmd_timers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /timers command — list all scheduled timers."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /timers attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    if not TIMERS:
        await update.message.reply_text("ℹ️ No timers scheduled.")
        return

    lines = ["⏰ *Scheduled Timers:*\n"]
    for timer_key in sorted(TIMERS.keys()):
        portions = TIMERS[timer_key]["portions"]
        lines.append(f"• `{timer_key}` — {portions} portion(s)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_deletetimer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /deletetimer HH:MM command — remove a scheduled timer."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized /deletetimer attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: `/deletetimer HH:MM`\nExample: `/deletetimer 08:00`",
            parse_mode="Markdown",
        )
        return

    timer_key = context.args[0]

    # Normalize format
    try:
        hour, minute = map(int, timer_key.split(":"))
        timer_key = f"{hour:02d}:{minute:02d}"
    except (ValueError, AttributeError):
        await update.message.reply_text(
            "⚠️ Invalid time format. Use HH:MM (e.g., 08:00)"
        )
        return

    if timer_key not in TIMERS:
        await update.message.reply_text(
            f"ℹ️ Timer `{timer_key}` not found.", parse_mode="Markdown"
        )
        return

    # Remove the timer
    try:
        job = TIMERS[timer_key].get("job")
        if job:
            job.schedule_removal()

        del TIMERS[timer_key]
        save_timers()

        logger.info("User %s (%d) deleted timer %s", user.full_name, user.id, timer_key)
        await update.message.reply_text(
            f"✅ Timer `{timer_key}` deleted.", parse_mode="Markdown"
        )
    except Exception as e:
        logger.exception("Failed to delete timer %s", timer_key)
        await update.message.reply_text(f"❌ Failed to delete timer: {e}")


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------


async def post_init(application: Application) -> None:
    """Initialize timers after the application is ready."""
    init_timers(application.job_queue)


def main() -> None:
    """Build and run the Telegram bot application."""
    logger.info("Starting Pet Feeder Bot...")

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("adduser", cmd_adduser))
    application.add_handler(CommandHandler("feed", cmd_feed))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("addtimer", cmd_addtimer))
    application.add_handler(CommandHandler("timers", cmd_timers))
    application.add_handler(CommandHandler("deletetimer", cmd_deletetimer))

    logger.info("Bot is polling for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
