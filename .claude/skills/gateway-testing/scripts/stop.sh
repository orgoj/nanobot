#!/bin/bash
SESSION="nanobot-gateway"
tmux kill-session -t $SESSION 2>/dev/null
echo "Gateway stopped."
