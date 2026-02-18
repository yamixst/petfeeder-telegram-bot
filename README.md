# 🐱 Cat Feeder Telegram Bot

A Telegram bot for controlling a Tuya-based automatic cat feeder over the local network using [TinyTuya](https://github.com/jasonacox/tinytuya).

## Features

- **Feed** — dispense a configurable number of food portions with one tap
- **Status** — query and display the current device state (data points)
- **Access control** — restrict bot usage to a whitelist of Telegram user IDs
- **Configuration file** — all settings live in a single `.conf` file (no hardcoded secrets)
- **Docker support** — run as a container with `docker compose`

## Prerequisites

- A Tuya-compatible automatic cat feeder on your local network
- Tuya device credentials (`device_id`, `local_key`) — see [TinyTuya Setup](https://github.com/jasonacox/tinytuya#setup)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- **Docker** and **Docker Compose** (recommended), or Python 3.10+

## Quick Start (Docker)

1. **Clone the repository:**

   ```
   git clone <repo-url>
   cd catfeeder-bot
   ```

2. **Create the configuration file:**

   ```
   cp catfeeder.conf.example catfeeder.conf
   ```

   Edit `catfeeder.conf` with your real credentials (see [Configuration](#configuration) below).

3. **Build and start the container:**

   ```
   docker compose up -d --build
   ```

4. **Check the logs:**

   ```
   docker compose logs -f
   ```

5. **Stop the bot:**

   ```
   docker compose down
   ```

> **Note:** The container runs with `network_mode: host` because tinytuya communicates with the feeder directly over the local network (UDP/TCP on LAN). This is required for device discovery and control.

## Deployment

The project includes a deployment script `deploy.sh` that automates the entire deployment process to a remote server.

### Usage

```bash
./deploy.sh USER@HOST:PATH [commit_message]
```

**Examples:**

Deploy with auto-generated commit message:
```bash
./deploy.sh xst@100.91.51.1:/home/xst/catfeeder
```

Deploy with custom commit message:
```bash
./deploy.sh xst@100.91.51.1:/home/xst/catfeeder "Fix feeding schedule bug"
```

### What the script does:

1. ✅ Checks for local changes
2. ✅ Commits changes to git (if any)
3. ✅ Pushes code to remote server via git
4. ✅ Copies `catfeeder.conf` via scp
5. ✅ Rebuilds Docker image on remote server
6. ✅ Restarts the container
7. ✅ Shows deployment status and logs

### First-time deployment setup:

1. **On the remote server**, initialize git repository:
   ```bash
   ssh USER@HOST
   cd /path/to/catfeeder
   git init
   git config receive.denyCurrentBranch updateInstead
   ```

2. **On your local machine**, add the remote:
   ```bash
   git remote add production ssh://USER@HOST/path/to/catfeeder
   ```

3. **Deploy using the script:**
   ```bash
   ./deploy.sh USER@HOST:/path/to/catfeeder "Initial deployment"
   ```

### Setting the timezone

By default the container uses UTC. To match your host timezone, set the `TZ` environment variable:

```
TZ=Europe/Moscow docker compose up -d --build
```

Or create a `.env` file next to `docker-compose.yml`:

```
TZ=Europe/Moscow
```

## Manual Installation (without Docker)

1. **Clone the repository:**

   ```
   git clone <repo-url>
   cd catfeeder-bot
   ```

2. **Create and activate a virtual environment:**

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**

   ```
   pip install -r requirements.txt
   ```

4. **Configure the bot:**

   ```
   cp catfeeder.conf.example catfeeder.conf
   ```

   Edit `catfeeder.conf` with your values (see [Configuration](#configuration) below).

5. **Run the bot:**

   ```
   python catfeeder_bot.py
   ```

## Configuration

All settings are stored in `catfeeder.conf` (INI format):

| Section      | Key                | Description                                         |
|--------------|--------------------|-----------------------------------------------------|
| `[telegram]` | `bot_token`        | Telegram Bot API token from @BotFather              |
| `[telegram]` | `allowed_user_ids` | Comma-separated list of authorized user IDs         |
| `[device]`   | `device_id`        | Tuya device ID                                      |
| `[device]`   | `ip_address`       | Local IP address of the feeder                      |
| `[device]`   | `local_key`        | Tuya local encryption key                           |
| `[device]`   | `version`          | Tuya protocol version (`3.1`, `3.3`, `3.4`, `3.5`) |
| `[device]`   | `feed_dp`          | Data point index for the feed command               |
| `[device]`   | `portions`         | Number of portions per feed command                 |
| `[logging]`  | `level`            | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`)     |
| `[logging]`  | `file`             | Log file path (leave empty for stdout only)         |

> **Tip:** Find your Telegram user ID by messaging [@userinfobot](https://t.me/userinfobot).

## Usage

Open your Telegram bot and send `/start`. You will see two inline buttons:

- 🍽 **Feed** — triggers the feeder to dispense food
- 📊 **Status** — shows current device data points

## Running as a systemd Service

If you prefer running without Docker, create `/etc/systemd/system/catfeeder-bot.service`:

```
[Unit]
Description=Cat Feeder Telegram Bot
After=network.target

[Service]
Type=simple
User=catfeeder
WorkingDirectory=/opt/catfeeder-bot
ExecStart=/opt/catfeeder-bot/.venv/bin/python catfeeder_bot.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```
sudo systemctl daemon-reload
sudo systemctl enable --now catfeeder-bot.service
```

## Security Notes

- **Never commit `catfeeder.conf`** — it contains secrets. It is already listed in `.gitignore`.
- The Docker image does **not** bake in the config — it is mounted as a read-only volume at runtime.
- The container runs as a **non-root** user (`appuser`, UID 1000).
- The bot only responds to users whose IDs are in the `allowed_user_ids` list.
- Communication with the feeder happens over the **local network** (LAN), not through Tuya cloud.

## Project Structure

```
catfeeder-bot/
├── catfeeder_bot.py        # Main bot application
├── catfeeder.conf          # Configuration file (not committed)
├── catfeeder.conf.example  # Example config safe to commit
├── catfeeder.py            # Original standalone script
├── docker-compose.yml      # Docker Compose service definition
├── Dockerfile              # Multi-stage container build
├── .dockerignore           # Files excluded from Docker build context
├── .gitignore              # Git ignore rules
├── logs/                   # Log files (Docker volume mount)
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

## License

This project is provided as-is for personal use.