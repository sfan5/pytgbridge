pytgbridge
==========

Telegram/IRC bridge

Uses [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) and [python-irc](https://github.com/jaraco/irc).

### How to
Create a bot on Telegram using [@BotFather](https://t.me/BotFather) and make sure to **disable** message privacy using `/setprivacy`.

```bash
pip install -e .
cp conf.json.example config.json
# Edit config.json with your favorite text editor
python -m pytgbridge
```

If you want to run it in background either use screen/tmux or the daemon functionality:

`$ python -m pytgbridge -q -D`

