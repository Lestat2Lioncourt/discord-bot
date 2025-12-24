#!/bin/bash
tmux new-session -d -s bot_session "source ~/Projects/discord_bot/venv/bin/activate && python ~/Projects/discord_bot/bot.py"
echo "Bot démarré dans une session tmux nommée 'bot_session'."
