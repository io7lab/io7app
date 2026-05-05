#!/bin/sh
# io7app container entrypoint.
#
# Watches /app (mounted by `docker run -v <host>:/app`) for app.py and .env.
# When both are present, runs `python /app/app.py`. Restarts on:
#   - any change to app.py or .env (live-reload while python runs)
#   - python exiting (clean or error) followed by a change to either file
# Loop never terminates.
#
# Only app.py and .env are watched. If the user splits their code across
# helper modules under /app, they should `touch app.py` (or .env) to force
# a reload after editing subordinate files.

set -u

APP_DIR=/app
APP_FILE="$APP_DIR/app.py"
ENV_FILE="$APP_DIR/.env"
PYTHON=/usr/local/bin/python
POLL_INTERVAL="${IO7_POLL_INTERVAL:-2}"

# As PID 1 we must explicitly forward shutdown signals to the python child;
# otherwise `docker stop` waits the full grace period and SIGKILLs everything,
# giving app.py no chance to clean up.
trap 'kill -TERM "${pypid:-0}" 2>/dev/null; exit 143' TERM INT

print_guide() {
    cat <<'EOF'

================================================================
  io7app container - waiting for application files in /app
================================================================

Mount your working folder into the container at /app:

    docker run --rm -it -v "$PWD":/app <image>

The folder must contain two files:

  1. app.py   - your io7app Python application
  2. .env     - environment variables for the io7 broker

------------------- example .env -------------------
IO7_SERVER=iot201.ddns.net
IO7_APP_ID=app3
IO7_TOKEN=app3
# IO7_PORT=1883     # optional; auto 8883 when TLS engages
# IO7_CA=ca.pem     # optional; or place ca.pem in cwd
# IO7_LOG=ERROR     # DEBUG|INFO|WARNING|ERROR|CRITICAL
----------------------------------------------------

------------------- example app.py -----------------
from io7app import App

app = App()

@app.on_event("sw1", "status")
def on_switch(data):
    print("sw1 ->", data)

app.run()
----------------------------------------------------

Live reload:
  Saving app.py or .env restarts the container automatically.
  If you edit other files (helpers.py, config files, etc.),
  run `touch app.py` to trigger a reload.

EOF
}

mtime() {
    stat -c %Y "$1" 2>/dev/null || echo 0
}

files_ready() {
    [ -f "$APP_FILE" ] && [ -f "$ENV_FILE" ]
}

wait_until_ready() {
    until files_ready; do
        sleep "$POLL_INTERVAL"
    done
}

stop_child() {
    pid=$1
    kill -TERM "$pid" 2>/dev/null
    i=0
    while [ "$i" -lt 5 ] && kill -0 "$pid" 2>/dev/null; do
        sleep 1
        i=$((i + 1))
    done
    kill -KILL "$pid" 2>/dev/null
}

cd "$APP_DIR" || exit 1

while true; do
    if ! files_ready; then
        print_guide
        echo ">>> Monitoring $APP_DIR for app.py and .env ..."
        wait_until_ready
        echo ">>> Detected app.py and .env. Starting application."
    fi

    a0=$(mtime "$APP_FILE")
    e0=$(mtime "$ENV_FILE")

    echo ">>> Running: $PYTHON -u $APP_FILE"
    echo "----------------------------------------------------------------"
    # -u: unbuffered stdout/stderr so tracebacks and print() output appear
    # in `docker logs` and on the terminal in real time, not after the
    # process exits.
    "$PYTHON" -u "$APP_FILE" &
    pypid=$!

    changed=0
    while kill -0 "$pypid" 2>/dev/null; do
        sleep "$POLL_INTERVAL"
        if [ "$(mtime "$APP_FILE")" != "$a0" ] || [ "$(mtime "$ENV_FILE")" != "$e0" ]; then
            changed=1
            echo ""
            echo ">>> Change detected in app.py or .env. Restarting."
            stop_child "$pypid"
            break
        fi
    done

    wait "$pypid" 2>/dev/null
    status=$?
    echo "----------------------------------------------------------------"

    if [ "$changed" = 1 ]; then
        continue
    fi

    if [ "$status" -eq 0 ]; then
        echo ">>> app.py exited cleanly (status 0)."
        print_guide
    else
        echo ""
        echo "################################################################"
        echo "# app.py exited with ERROR (status $status)"
        echo "# See the traceback above for details."
        echo "################################################################"
    fi

    echo ">>> Monitoring app.py and .env for changes (touch either to restart) ..."

    a0=$(mtime "$APP_FILE")
    e0=$(mtime "$ENV_FILE")
    while files_ready; do
        sleep "$POLL_INTERVAL"
        if [ "$(mtime "$APP_FILE")" != "$a0" ] || [ "$(mtime "$ENV_FILE")" != "$e0" ]; then
            break
        fi
    done
    echo ">>> Change detected. Restarting."
done
