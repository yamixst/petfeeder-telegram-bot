#!/usr/bin/env python3
"""Telegram bot for controlling a Tuya-based automatic cat feeder.

Provides /start command with inline keyboard buttons:
  - Feed: dispenses a configured number of food portions
  - Status: queries and displays the current device state
"""

import configparser
import logging
import sys
from pathlib import Path
from typing import Final

import tinytuya
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CONFIG_PATH: Final[str] = str(Path(__file__).resolve().parent / "catfeeder.conf")


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

# Logging settings
LOG_LEVEL: Final[str] = CONFIG.get("logging", "level", fallback="INFO").upper()
LOG_FILE: Final[str] = CONFIG.get("logging", "file", fallback="")

# Callback data constants
CB_FEED: Final[str] = "feed"
CB_STATUS: Final[str] = "status"

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
# Keyboard builder
# ---------------------------------------------------------------------------


def build_main_keyboard() -> InlineKeyboardMarkup:
    """Build the main inline keyboard with Feed and Status buttons.

    Returns:
        InlineKeyboardMarkup with two buttons.
    """
    keyboard = [
        [
            InlineKeyboardButton("🍽 Feed", callback_data=CB_FEED),
            InlineKeyboardButton("📊 Status", callback_data=CB_STATUS),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


# ---------------------------------------------------------------------------
# Bot handlers
# ---------------------------------------------------------------------------


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command — greet the user and show the main keyboard."""
    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized access attempt from user %s", user)
        await update.message.reply_text("⛔ Access denied.")
        return

    logger.info("User %s (%d) started the bot", user.full_name, user.id)
    await update.message.reply_text(
        f"👋 Hello, {user.first_name}!\n\n"
        "Use the buttons below to control the cat feeder:",
        reply_markup=build_main_keyboard(),
    )


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


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route inline‑keyboard button presses to the appropriate action."""
    query = update.callback_query
    if query is None:
        return

    await query.answer()

    user = update.effective_user
    if user is None or not is_authorized(user.id):
        logger.warning("Unauthorized callback from user %s", user)
        await query.edit_message_text("⛔ Access denied.")
        return

    if query.data == CB_FEED:
        await handle_feed(query, user)
    elif query.data == CB_STATUS:
        await handle_status(query, user)
    else:
        logger.warning("Unknown callback data: %s", query.data)


async def handle_feed(query, user) -> None:
    """Process the Feed button press.

    Sends a feed command and reports the result back to the user.
    """
    logger.info("User %s (%d) requested feeding", user.full_name, user.id)

    try:
        result = trigger_feed()
        error = result.get("Error") if isinstance(result, dict) else None

        if error:
            text = f"⚠️ Feed command sent but device returned an error:\n`{error}`"
            logger.error("Feed error: %s", error)
        else:
            text = f"✅ Fed the cat! Dispensed {PORTIONS} portion(s)."
    except Exception:
        logger.exception("Failed to send feed command")
        text = "❌ Failed to communicate with the feeder. Check the device connection."

    await query.edit_message_text(text, reply_markup=build_main_keyboard())


async def handle_status(query, user) -> None:
    """Process the Status button press.

    Queries the device status and displays it to the user.
    """
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

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=build_main_keyboard(),
    )


# ---------------------------------------------------------------------------
# Application entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Build and run the Telegram bot application."""
    logger.info("Starting Cat Feeder Bot...")

    application = Application.builder().token(BOT_TOKEN).build()

    # Register handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("myid", cmd_myid))
    application.add_handler(CommandHandler("adduser", cmd_adduser))
    application.add_handler(CallbackQueryHandler(handle_callback))

    logger.info("Bot is polling for updates...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
