import socket
import sys
import time
import select

# A practical* real-world** implementation of an Internet Relay Chat client
# * : This means I didn't read the RFC
# **: This means it only implements whatever niche usecase I had at that time

__all__ = ["BaseIRCClient"]

def connect_socket(host, port, ipv6=True, ssl=False):
	family = 0 if ipv6 else socket.AF_INET
	ai = socket.getaddrinfo(host, port, family=family, proto=socket.IPPROTO_TCP)
	s = socket.socket(*ai[0][:2])
	s.connect(ai[0][4])

	if ssl:
		ctx = __import__("ssl").create_default_context()
		s = ctx.wrap_socket(s, server_hostname=host)
	return s

def enable_keepalive(sock, interval_sec):
	sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
	if sys.platform.startswith("linux"):
		sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 120)
		sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, interval_sec)
		sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
	elif sys.platform.startswith("darwin"):
		sock.setsockopt(socket.IPPROTO_TCP, 0x10, interval_sec)
	elif sys.platform.startswith("win"):
		sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60000, interval_sec * 1000))

class Readline():
	def __init__(self):
		self.reset()
	def reset(self):
		self.buf = b""
	def readline(self, sock, delim=b'\n', limit=1024):
		data = sock.recv(limit)
		if not data: return
		i = 0
		while True:
			i2 = data.find(delim, i)
			if i2 == -1:
				self.buf += data[i:]
				break
			yield self.buf + data[i:i2]
			self.buf = b""
			i = i2 + len(delim)

def decode_bytes(b):
	try:
		return b.decode('utf-8')
	except UnicodeDecodeError:
		return b.decode('latin-1')

def parse_line(s):
	ret = []
	i = 0
	while True:
		i2 = s.find(" ", i)
		if i2 == -1: break

		text = s[i:i2]
		if text.startswith(":") and i > 0:
			return ret, s[i+1:]
		ret.append(text)
		i = i2 + 1
	text = s[i:]
	if text.startswith(":") and i > 0:
		return ret, text[1:]
	return ret + [text], None

class Params():
	def __init__(self, **kwargs):
		for k, v in kwargs.items():
			setattr(self, k, v)

def log_error(e):
	# TODO eventually remove this
	print(">>", e, "<<")

class BaseIRCClient():
	def __init__(self, nick, server, port=6667, ipv6=True, ssl=False, realname="IRC client", password=None):
		self.conn_params = Params( args=(server, port), kwargs={"ipv6": ipv6, "ssl": ssl} )
		self.user_params = Params(nick=nick, realname=realname, password=password)
		self.s = None
		self.connect()
	def _send(self, fields, fulltext=None):
		b = " ".join(fields)
		if fulltext is not None:
			b += " :" + fulltext
		b = b.encode('utf-8') + b"\r\n"
		if len(b) > 512:
			raise ValueError("irc message too long")

		if self.s is None:
			return # uhh...
		try:
			self.s.send(b)
		except socket.error as e:
			log_error(e)
			self.disconnect()
	def _handle(self, fields, fulltext):
		prefix = None
		if fields[0].startswith(":"):
			prefix = fields[0][1:]
			del fields[0]

		cmd = fields[0].upper()
		if cmd == "001": # RPL_WELCOME
			self.on_connected()
		elif cmd in ("432", "433", "436"): # ERR_ERRONEUSNICKNAME, ERR_NICKNAMEINUSE, ERR_NICKCOLLISION
			self.on_nickerror(cmd)
		elif cmd == "PING":
			self._send(["PONG"] + fields[1:], fulltext)
		elif cmd == "JOIN":
			if len(fields) == 1: fields += [fulltext] # workaround for InspIRCd
			self.on_join(fields[1], prefix)
		elif cmd == "PRIVMSG":
			if len(fulltext) > 2 and fulltext.startswith("\x01") and fulltext.endswith("\x01"):
				i = fulltext.find(" ")
				type = fulltext[1:i] # -1 happens to be the value we want if not found
				msg = None if i == -1 else fulltext[i+1:-1]
				return self.on_ctcp(fields[1], prefix, type, msg)
			self.on_privmsg(fields[1], prefix, fulltext)
		elif cmd == "PART":
			self.on_part(fields[1], prefix, fulltext)
		elif cmd == "KICK":
			self.on_kick(fields[1], prefix, fields[2], fulltext)


	# arguments used here:
	#   source: "nickname!user@host.name"
	#   target: "nickname" or "#channel"
	#   kicked: "nickname"
	#   err, type, msg: arbitrary strings
	def on_connected(self):
		...
	def on_disconnect(self):
		...
	def on_nickerror(self, err):
		...
	def on_join(self, target, source):
		...
	def on_privmsg(self, target, source, msg):
		...
	def on_ctcp(self, target, source, type, msg):
		...
	def on_part(self, target, source, msg):
		...
	def on_kick(self, target, source, kicked, msg):
		...


	def run(self):
		rl = Readline()
		while True:
			if self.s is None:
				rl.reset()
				time.sleep(1) # since the socket isn't open, there is nothing to do for us
				continue
			rlist, _, _ = select.select([self.s], [], [])
			if len(rlist) == 0:
				continue

			try:
				data = list(rl.readline(self.s))
			except socket.error as e:
				log_error(e)
				rl.reset()
				self.disconnect()
				continue

			for line in data:
				line = line.rstrip(b"\r\n")
				line = decode_bytes(line)
				fields, fulltext = parse_line(line)
				self._handle(fields, fulltext)
	def connect(self):
		if self.s is not None:
			self.disconnect()
		try:
			self.s = connect_socket(*self.conn_params.args, **self.conn_params.kwargs)
		except socket.error as e:
			log_error(e)
			return self.disconnect()
		enable_keepalive(self.s, 30) # i don't feel like implementing repeated PINGs

		if self.user_params.password is not None:
			self._send(["PASS", self.user_params.password])
		self._send(["NICK", self.user_params.nick])
		self._send(["USER", "tanoshii", "8", "*"], self.user_params.realname)
	def disconnect(self):
		if self.s is not None:
			self.s.close()
		self.s = None
		self.on_disconnect()

	def get_nick(self):
		return self.user_params.nick

	def nick(self, nick):
		self._send(["NICK", nick])
		self.user_params.nick = nick
	def join(self, channel, key=None):
		self._send(["JOIN", channel], key)
	def privmsg(self, target, msg):
		self._send(["PRIVMSG", target], msg)
	def ctcp(self, target, type, msg=None):
		s = "\x01" + type
		if msg is not None:
			s += " " + msg
		self.privmsg(target, s + "\x01")
	def part(self, channel, msg="Leaving"):
		self._send(["PART", channel], msg)
	def kick(self, channel, nick, msg="Kicked"):
		self._send(["KICK", channel, nick], msg)
	def quit(self, msg="Quit"):
		self._send(["QUIT"], msg)

