pytgbridge
==========

Telegram/IRC bridge

You'll need [pyTelegramBotAPI](https://github.com/eternnoir/pyTelegramBotAPI) and [python-irc](https://github.com/jaraco/irc).

### How to
```
$ pip3 install -r requirements.txt
$ cp conf.json.example config.json
Edit config.json with your favorite text editor.
$ ./pytgbridge
```

If you want to run it in background either use screen/tmux or the daemon functionality:

`$ ./pytgbridge -q -D`

