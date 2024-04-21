import irc.connection
import irc.bot
import socket
import logging
import time
from jaraco.stream import buffer

MESSAGE_SPLIT_LEN = 420

class IRCEvent():
	def __init__(self, orig, argname="message"):
		self.nick, self.mask = orig.source.split("!")
		self.channel = orig.target if orig.target.startswith("#") else None
		setattr(self, argname, orig.arguments[0] if len(orig.arguments) > 0 else None)

class IRCBot(irc.bot.SingleServerIRCBot):
	def __init__(self, args, kwargs=None, ns_password=None):
		kwargs = kwargs or {}
		irc.bot.SingleServerIRCBot.__init__(self, *args, **kwargs)
		self.connection.buffer_class = buffer.LenientDecodingLineBuffer
		self.event_handlers = {}
		self.ns_password = ns_password

	def _invoke_event_handler(self, name, args=(), kwargs=None):
		if name not in self.event_handlers.keys():
			logging.warning("Unhandeled '%s' event", name)
			return
		kwargs = kwargs or {}
		try:
			self.event_handlers[name](*args, **kwargs)
		except Exception:
			logging.exception("Exception in IRC event handler")


	def on_welcome(self, conn, event):
		logging.info("IRC connection established")
		if self.ns_password is not None:
			self.connection.privmsg("NickServ", "IDENTIFY " + self.ns_password)
		self._invoke_event_handler("connected")

	def on_nicknameinuse(self, conn, event):
		self._invoke_event_handler("nick_in_use")

	def on_privmsg(self, conn, event):
		self._invoke_event_handler("message", (IRCEvent(event), ))

	def on_pubmsg(self, conn, event):
		self._invoke_event_handler("message", (IRCEvent(event), ))

	def on_action(self, conn, event):
		self._invoke_event_handler("action", (IRCEvent(event), ))

	def on_join(self, conn, event):
		if event.source.split("!")[0] == conn.get_nickname():
			return
		self._invoke_event_handler("join", (IRCEvent(event), ))

	def on_part(self, conn, event):
		self._invoke_event_handler("part", (IRCEvent(event), ))

	def on_kick(self, conn, event):
		if event.arguments[0] == conn.get_nickname():
			conn.join(event.target)
			return
		self._invoke_event_handler("kick", (IRCEvent(event, argname="othernick"), ))

	def on_disconnect(self, conn, event):
		logging.warning("IRC connection error, reconnecting")
		time.sleep(5)
		self.jump_server()

class IRCClient():
	def __init__(self, config):
		# Read config
		args = {}
		args["ipv6"] = True if "ipv6" not in config.keys() else config["ipv6"]
		if config["ssl"]:
			args["wrapper"] = __import__("ssl").wrap_socket
		# Resolve host
		family = 0 if args["ipv6"] else socket.AF_INET
		try:
			ai = socket.getaddrinfo(config["server"], 0, family=family, proto=socket.IPPROTO_TCP)
		except socket.gaierror as e:
			logging.error("Failed to resolve hostname: %r", e)
			exit(1)
		args["ipv6"] = args["ipv6"] and ai[0][0] == socket.AF_INET6 # this determines the socket type used
		host = ai[0][4][0]
		if "password" in config.keys():
			serv = (host, config["port"], config["password"])
		else:
			serv = (host, config["port"])
		# Actually create bot with correct params
		kwargs = {"connect_factory": irc.connection.Factory(**args)}
		args = [[serv], config["nick"], "pytgbridge (IRC)"]
		ns_password = None if "nickpassword" not in config.keys() else config["nickpassword"]
		self.bot = IRCBot(args, kwargs, ns_password=ns_password)
	def run(self):
		self.bot.start()
	def event_handler(self, name, func):
		self.bot.event_handlers[name] = func

	def join(self, channel):
		self.bot.connection.join(channel)
	def privmsg(self, target, message):
		if len(message) < MESSAGE_SPLIT_LEN:
			msgs = [message]
		else:
			msgs = []
			for i in range(0, len(message), MESSAGE_SPLIT_LEN):
				msgs.append(message[i:i + MESSAGE_SPLIT_LEN])
		try:
			for m in msgs:
				self.bot.connection.privmsg(target, m)
		except irc.client.ServerNotConnectedError:
			logging.warning("Dropping message because IRC not connected yet")
