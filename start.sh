#!/bin/bash
# AES Logistics — one-command launcher.
# Starts the server, opens a public HTTPS tunnel, and prints the URL to visit.
# Run it from WSL with:  bash start.sh
# (or double-click the Windows launcher, which calls this for you)

set -e
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR/server"

echo "=========================================="
echo "  AES Logistics Launcher"
echo "=========================================="
echo ""

# 1. Set up the Python environment the first time this runs
if [ ! -d "venv" ]; then
    echo "First run — setting up the Python environment (takes a minute)..."
    python3 -m venv venv
fi
source venv/bin/activate

echo "Checking dependencies..."
pip install -q -r requirements.txt

# 2. Set up .env the first time this runs
if [ ! -f ".env" ]; then
    echo ""
    echo "No .env file found yet — creating one from the template."
    cp .env.example .env
    SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s/replace-with-a-long-random-string/$SECRET/" .env
    echo ""
    echo "!! ACTION NEEDED: open server/.env and set ADMIN_EMAIL (e.g. an @aes-energy.com"
    echo "   address) and confirm SHARED_PASSWORD, then run this script again."
    echo ""
    exit 1
fi

# 3. Free up port 5000 if a previous run left something on it
fuser -k 5000/tcp 2>/dev/null || true
sleep 1

# 4. Start the server in the background
echo "Starting the server..."
nohup python3 app.py > /tmp/aes_logistics_server.log 2>&1 &
SERVER_PID=$!

for i in $(seq 1 15); do
    if curl -s http://127.0.0.1:5000/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! curl -s http://127.0.0.1:5000/api/health > /dev/null 2>&1; then
    echo ""
    echo "The server didn't start. Here's what it logged:"
    echo "------------------------------------------------"
    cat /tmp/aes_logistics_server.log
    echo "------------------------------------------------"
    exit 1
fi
echo "Server is running."
echo ""

# 5. Install cloudflared the first time this runs
if ! command -v cloudflared &> /dev/null; then
    echo "Installing the tunnel tool (one-time, first run only)..."
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
fi

# 6. Stop the server cleanly when this window is closed / Ctrl+C is pressed
trap 'echo ""; echo "Stopping server..."; kill $SERVER_PID 2>/dev/null; exit' INT TERM EXIT

# 7. Start the public tunnel — this prints the URL to open
echo "=========================================="
echo "  Starting your public link..."
echo "  Look for the https://....trycloudflare.com"
echo "  URL below once it appears."
echo "=========================================="
echo ""
cloudflared tunnel --url http://localhost:5000
