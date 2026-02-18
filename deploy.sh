#!/bin/bash

# Pet Feeder Bot Deployment Script
# Automates git commit, push, and Docker deployment
# Usage: ./deploy.sh USER@HOST:PATH [commit_message]

set -e  # Exit on error

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

# Parse remote target from command line
if [ -z "$1" ]; then
    log_error "Usage: $0 USER@HOST:PATH [commit_message]"
    log_error "Example: $0 xst@100.91.51.1:/home/xst/petfeeder 'Fix bug'"
    exit 1
fi

REMOTE_TARGET="$1"
shift  # Remove first argument, rest are commit message

# Parse USER@HOST:PATH format
if [[ ! "$REMOTE_TARGET" =~ ^([^@]+)@([^:]+):(.+)$ ]]; then
    log_error "Invalid format. Expected: USER@HOST:PATH"
    log_error "Example: xst@100.91.51.1:/home/xst/petfeeder"
    exit 1
fi

REMOTE_USER="${BASH_REMATCH[1]}"
REMOTE_HOST="${BASH_REMATCH[2]}"
REMOTE_PATH="${BASH_REMATCH[3]}"
REMOTE_NAME="production"

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
    log_info "Remote: $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH"

    # Check for changes
    if check_changes; then
        # Show status
        log_info "Changes detected:"
        git status -s

        # Get commit message
        if [ -z "$1" ]; then
            COMMIT_MSG="Deploy: $(date '+%Y-%m-%d %H:%M:%S')"
        else
            COMMIT_MSG="$*"
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
    if [ -f "petfeeder.conf" ]; then
        log_info "Copying configuration file..."
        scp petfeeder.conf $REMOTE_USER@$REMOTE_HOST:$REMOTE_PATH/
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
