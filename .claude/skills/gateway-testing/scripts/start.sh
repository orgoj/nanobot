#!/bin/bash
SESSION="nanobot-gateway"
tmux has-session -t $SESSION 2>/dev/null
if [ $? -eq 0 ]; then
    tmux kill-session -t $SESSION
fi
# Spustíme gateway a logujeme stdout do souboru
tmux new-session -d -s $SESSION "uv run nanobot gateway > ~/.nanobot/logs/gateway_stdout.log 2>&1"
echo "Gateway started in tmux session: $SESSION"
