import irc.connection
import irc.bot
import logging

class IRCEvent():
	def __init__(self, orig):
		self.nick, self.mask = orig.source.split("!")
		self.channel = orig.target if orig.target.startswith("#") else None
		self.message = orig.arguments[0]

class IRCBot(irc.bot.SingleServerIRCBot):
	def __init__(self, args, kwargs={}):
		irc.bot.SingleServerIRCBot.__init__(self, *args, **kwargs)
		self.event_handlers = {}
	
	def _invoke_event_handler(self, name, args=(), kwargs={}):
		if name not in self.event_handlers.keys():
			logging.warning("Unhandeled '%s' event", name)
			return
		try:
			self.event_handlers[name](*args, **kwargs)
		except Exception as e:
			logging.exception("Exception in IRC event handler")


	def on_welcome(self, conn, event):
		logging.info("IRC connection established")
		self._invoke_event_handler("connected")

	def on_nicknameinuse(self, conn, event):
		self._invoke_event_handler("nick_in_use")

	def on_privmsg(self, conn, event):
		self._invoke_event_handler("message", (IRCEvent(event), ))

	def on_pubmsg(self, conn, event):
		self._invoke_event_handler("message", (IRCEvent(event), ))

	def on_action(self, conn, event):
		self._invoke_event_handler("action", (IRCEvent(event), ))

class IRCClient():
	def __init__(self, config):
		args = {"ipv6": True}
		if config["ssl"]:
			args["wrapper"] = __import__("ssl").wrap_socket
		kwargs = {"connect_factory": irc.connection.Factory(**args)}
		args = [[(config["server"], config["port"])], config["nick"], "pytgbridge (IRC)"]
		self.bot = IRCBot(args, kwargs)
	def run(self):
		self.bot.start()
	def event_handler(self, name, func):
		self.bot.event_handlers[name] = func

	def join(self, channel):
		self.bot.connection.join(channel)
	def privmsg(self, target, message):
		self.bot.connection.privmsg(target, message)

