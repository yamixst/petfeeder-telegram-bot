#!/bin/bash

# Catfeeder Bot Deployment Script
# Automates git commit, push, and Docker deployment

set -e  # Exit on error

# Configuration
REMOTE_USER="xst"
REMOTE_HOST="100.91.51.1"
REMOTE_PATH="/home/xst/catfeeder"
REMOTE_NAME="production"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if there are changes to commit
check_changes() {
    if [[ -z $(git status -s) ]]; then
        log_warn "No changes to commit"
        return 1
    fi
    return 0
}

# Main deployment process
main() {
    log_info "Starting deployment process..."

    # Check for changes
    if check_changes; then
        # Show status
        log_info "Changes detected:"
        git status -s

        # Get commit message
        if [ -z "$1" ]; then
            COMMIT_MSG="Deploy: $(date '+%Y-%m-%d %H:%M:%S')"
        else
            COMMIT_MSG="$1"
        fi

        # Add all changes
        log_info "Adding changes to git..."
        git add -A

        # Commit
        log_info "Committing with message: $COMMIT_MSG"
        git commit -m "$COMMIT_MSG"
    else
        log_info "No changes to commit, deploying current version..."
    fi

    # Push to remote
    log_info "Pushing to production server..."
    git push $REMOTE_NAME main:master

    # Copy config if it exists and has changed
    if [ -f "catfeeder.conf" ]; then
        log_info "Copying configuration file..."
        scp catfeeder.conf $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/
    fi

    # Rebuild and restart on remote server
    log_info "Rebuilding Docker image and restarting container..."
    ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_PATH && docker compose up -d --build"

    # Wait a moment for container to start
    sleep 3

    # Show status
    log_info "Checking deployment status..."
    ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_PATH && docker compose ps"

    # Show recent logs
    log_info "Recent logs:"
    ssh $REMOTE_USER@$REMOTE_HOST "cd $REMOTE_PATH && docker compose logs --tail=20"

    log_info "Deployment completed successfully! 🚀"
}

# Run main function with all arguments
main "$@"
