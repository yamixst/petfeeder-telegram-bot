# 🐱 Cat Feeder Bot

A Telegram bot for controlling a [Tuya](https://www.tuya.com/)-based automatic cat feeder over the local network.

Feed your cat on demand or set up scheduled daily feedings — all from a Telegram chat.

## Features

- **On-demand feeding** — dispense food portions with a single `/feed` command
- **Device status** — query the feeder's current state and data points
- **Scheduled timers** — set up recurring daily feedings at specific times
- **Multi-user access** — authorize additional Telegram users on the fly
- **Local communication** — talks directly to the Tuya device on your LAN via [tinytuya](https://github.com/jasonacox/tinytuya) (no cloud dependency)
- **Docker-ready** — ships with a multi-stage `Dockerfile` and `docker-compose.yml`
- **Persistent config** — timers and user list survive restarts

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Greet and verify access |
| `/help` | Show available commands |
| `/myid` | Get your Telegram user ID (no auth required) |
| `/feed` | Dispense food (configured number of portions) |
| `/status` | Query and display the device state |
| `/addtimer HH:MM portions` | Schedule a daily feeding (e.g. `/addtimer 08:00 2`) |
| `/timers` | List all scheduled feedings |
| `/deletetimer HH:MM` | Remove a scheduled feeding |
| `/adduser <user_id>` | Add a Telegram user to the allowed list |

## Prerequisites

- **Python 3.12+**
- A **Tuya-compatible automatic cat feeder** on your local network
- Tuya device credentials (`device_id`, `local_key`) — see the [tinytuya setup guide](https://github.com/jasonacox/tinytuya#setup)
- A **Telegram Bot token** from [@BotFather](https://t.me/BotFather)
- **Docker** and **Docker Compose** (for containerized deployment)

## Quick Start

### 1. Clone the repository

```
git clone https://github.com/YOUR_USERNAME/catfeeder-bot.git
cd catfeeder-bot
```

### 2. Create the configuration file

```
cp catfeeder.conf.example catfeeder.conf
```

Edit `catfeeder.conf` and fill in your values:

```ini
[telegram]
bot_token = YOUR_BOT_TOKEN_HERE
allowed_user_ids = 123456789

[device]
device_id = YOUR_DEVICE_ID
ip_address = 192.168.1.100
local_key = YOUR_LOCAL_KEY
version = 3.5
feed_dp = 3
portions = 1

[logging]
level = INFO
file = catfeeder.log
```

> **Tip:** Use [@userinfobot](https://t.me/userinfobot) on Telegram to find your user ID, or send `/myid` to the bot once it's running.

### 3. Run with Docker Compose (recommended)

```
docker compose up -d --build
```

The bot uses **host networking** so that `tinytuya` can reach the feeder over your local network.

Check logs:

```
docker compose logs -f
```

### 4. Run without Docker

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python catfeeder_bot.py
```

## Configuration Reference

### `[telegram]`

| Option | Description |
|---|---|
| `bot_token` | Telegram Bot API token from @BotFather |
| `allowed_user_ids` | Comma-separated list of authorized Telegram user IDs |

### `[device]`

| Option | Description |
|---|---|
| `device_id` | Tuya device ID |
| `ip_address` | Local IP address of the feeder |
| `local_key` | Tuya device local key |
| `version` | Tuya protocol version (`3.1`, `3.3`, `3.4`, or `3.5`) |
| `feed_dp` | Data point index that triggers feeding |
| `portions` | Default number of portions per feed command |

### `[general]`

| Option | Description | Default |
|---|---|---|
| `timezone` | IANA timezone for timer scheduling (e.g. `Europe/Moscow`) | `UTC` |

### `[logging]`

| Option | Description | Default |
|---|---|---|
| `level` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | `INFO` |
| `file` | Log file path (empty = stdout only) | _(empty)_ |

## Docker

The project includes a production-ready Docker setup:

- **Multi-stage build** — keeps the final image small
- **Non-root user** — runs as `appuser` (UID 1000) for security
- **Health check** — built-in process liveness check
- **Host networking** — required for local Tuya device communication
- **Volume mounts** — config file (read-only) and logs directory are mounted from the host

### Environment Variables

| Variable | Description | Default |
|---|---|---|
| `TZ` | Container timezone (for log timestamps) | `UTC` |

## Deployment

A deployment script is included for pushing updates to a remote server:

```
./deploy.sh USER@HOST:/path/to/catfeeder-bot "Optional commit message"
```

The script will:

1. Commit and push local changes via Git
2. Copy the config file to the remote server (if present)
3. Rebuild the Docker image and restart the container on the remote host
4. Display deployment status and recent logs

## Project Structure

```
catfeeder-bot/
├── catfeeder_bot.py          # Main bot application
├── catfeeder.conf.example    # Example configuration file
├── requirements.txt          # Python dependencies
├── Dockerfile                # Multi-stage Docker build
├── docker-compose.yml        # Docker Compose service definition
├── deploy.sh                 # Deployment automation script
├── .gitignore
└── .dockerignore
```

## Dependencies

| Package | Purpose |
|---|---|
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) `>=21.0` | Telegram Bot API framework (with job queue for timers) |
| [tinytuya](https://github.com/jasonacox/tinytuya) `>=1.13.0` | Local Tuya device communication |

## Obtaining Tuya Device Credentials

To control your feeder locally, you need the `device_id`, `local_key`, and protocol `version`. Follow the [tinytuya setup instructions](https://github.com/jasonacox/tinytuya#setup) which involves:

1. Creating a Tuya IoT developer account
2. Linking your Tuya/Smart Life app
3. Running `python -m tinytuya wizard` to extract credentials

You can also use `python -m tinytuya scan` to discover the device's local IP address and protocol version.

## License

This project is provided as-is for personal use.