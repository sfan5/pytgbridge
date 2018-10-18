import logging
import time
import os
import random

from .irc_impl import BaseIRCClient

MESSAGE_SPLIT_LEN = 420

class IRCEvent():
	def __init__(self, target, source, **kwargs):
		self.nick, self.maks = source.split("!")
		self.channel = target if target.startswith("#") else None
		for k, v in kwargs.items():
			setattr(self, k, v)

class IRCBot(BaseIRCClient):
	def __init__(self, args, kwargs=None, ns_password=None):
		self.event_handlers = {}
		self.ns_password = ns_password
		self.reconnect_counter = 0
		kwargs = kwargs or {}
		super().__init__(*args, **kwargs)
	def _invoke_event_handler(self, name, args=(), kwargs=None):
		if name not in self.event_handlers.keys():
			logging.warning("Unhandeled '%s' event", name)
			return
		kwargs = kwargs or {}
		try:
			self.event_handlers[name](*args, **kwargs)
		except Exception:
			logging.exception("Exception in IRC event handler")


	def on_connected(self):
		logging.info("IRC connection established")
		self.reconnect_counter = 0
		if self.ns_password is not None:
			self.privmsg("NickServ", "IDENTIFY " + self.ns_password)
		self._invoke_event_handler("connected")

	def on_nickerror(self, err):
		#self._invoke_event_handler("nick_in_use")
		self.nick("Guest%d" % random.randint(1, 99999))

	def on_join(self, target, source):
		if source.split("!")[0] == self.get_nick():
			return
		self._invoke_event_handler("join", (IRCEvent(target, source), ))

	def on_privmsg(self, target, source, msg):
		self._invoke_event_handler("message", (IRCEvent(target, source, message=msg), ))

	def on_ctcp(self, target, source, type, msg):
		if type.upper() == "PING":
			self.ctcp(source.split("!")[0], type, msg)
		elif type.upper() == "ACTION":
			self._invoke_event_handler("action", (IRCEvent(target, source, message=msg), ))

	def on_part(self, target, source, msg):
		self._invoke_event_handler("part", (IRCEvent(target, source), ))

	def on_kick(self, target, source, kicked, msg):
		if kicked == self.get_nick():
			return self.join(target)
		self._invoke_event_handler("kick", (IRCEvent(target, source, othernick=kicked), ))

	def on_disconnect(self):
		self.reconnect_counter += 1
		if self.reconnect_counter > 10:
			logging.error("Reconnecting to IRC failed after 10 tries, exiting")
			os._exit(1)
		logging.warning("IRC connection error, reconnecting")
		time.sleep(5)
		self.connect()

def _wrap_ssl(sock):
	import ssl
	context = ssl.create_default_context()
	context.check_hostname = False
	context.verify_mode = ssl.CERT_NONE
	return context.wrap_socket(sock)

class IRCClient():
	def __init__(self, config):
		# Read config
		args = (config["nick"], config["server"])
		kwargs = {
			"port": config["port"],
			"ipv6": config.get("ipv6", True),
			"ssl": config["ssl"],
			"ssl_verify": config.get("ssl_verify", True),
			"realname": "pytgbridge (IRC)",
			"password": config.get("password", None)
		}

		ns_password = config.get("nickpassword", None)
		self.bot = IRCBot(args, kwargs, ns_password=ns_password)
	def run(self):
		self.bot.run()
	def event_handler(self, name, func):
		self.bot.event_handlers[name] = func

	def join(self, channel):
		self.bot.join(channel)
	def privmsg(self, target, message):
		if len(message) < MESSAGE_SPLIT_LEN:
			msgs = [message]
		else:
			msgs = []
			for i in range(0, len(message), MESSAGE_SPLIT_LEN):
				msgs.append(message[i:i + MESSAGE_SPLIT_LEN])
		for m in msgs:
			self.bot.privmsg(target, m)
