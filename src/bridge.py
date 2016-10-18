import re
import logging
from collections import namedtuple

def dump(obj, name): ##DEBUG##
	for e in dir(obj):
		if e.startswith("_"):
			continue
		print("%s.%s = %r" % (name, e, getattr(obj, e)))

def format_audio_duration(d):
	m, s = divmod(d, 60)
	if m == 0:
		return "%ds" % s
	elif m > 0 and s == 0:
		return "%dm" % m
	return "%dm%ds" % (m, s)

class NickColorizer():
	def __init__(self, config=None):
		if config is None:
			self.colors = [2, 3, 4, 7, 9, 10, 11, 12]
		else:
			self.colors = list(config)
	@staticmethod
	def _hash(s):
		v = 0
		for c in s:
			v += ord(c)
			v = (v << 2) & 0xffff | (v >> 14) # ROR by 2 bits
		return v
	def colorize(self, s):
		if len(self.colors) == 0: # disabled
			return s
		color = NickColorizer._hash(s) % len(self.colors)
		color = self.colors[color]
		return "\x03%02d%s\x0f" % (color, s)

class TextFormattingConverter():
	def __init__(self, enabled):
		self.enabled = enabled
		tmp = namedtuple("StyleCombo", ["open", "close"])
		if self.enabled:
			self.bold = tmp(open="<b>", close="</b>")
			self.italics = tmp(open="<i>", close="</i>")
		else:
			self.bold = self.italics = tmp(open="", close="")
	def irc2html(self, text):
		bold, italics = False, False
		skip_digits = 0
		ret = ""
		for c in text:
			if skip_digits > 0:
				skip_digits = (skip_digits - 1) if c.isdigit() else 0
				continue
			# Handle styles
			if c == "\x02":
				ret += self.bold.close if bold else self.bold.open
				bold = not bold
			elif c == "\x03": # color (ignored)
				skip_digits = 2
			elif c == "\x0f": # reset
				if bold:
					ret += self.bold.close
				if italics:
					ret += self.italics.close
				bold, italics = False, False
			elif c == "\x1d":
				ret += self.italics.close if italics else self.italics.open
				italics = not italics
			elif c == "\x1f": # underline (ignored)
				pass
			else:
				# Handle text: escape if required and pass through
				if c in ("<", ">", "&"):
					c = "&#" + str(ord(c)) + ";"
				ret += c
		if bold:
			ret += self.bold.close
		if italics:
			ret += self.italics.close
		return ret
				
	def html2irc(self, text):
		# TODO: Is this even possible with Telegram's Bot API?
		return text

LinkTuple = namedtuple("LinkTuple", ["telegram", "irc"])
config_names = [
	"telegram_bold_nicks",
	"irc_nick_colors",

	"forward_sticker_dimensions",
	"forward_document_mime",
	"forward_audio_description",
	"forward_text_formatting",
]

class Bridge():
	def __init__(self, tg, irc, wb, config):
		self.tg = tg
		self.irc = irc
		self.web = wb
		#
		self.links = set(LinkTuple(**e) for e in config["links"])
		logging.info("%d link(s) configured", len(self.links))
		if "irc_nick_colors" not in config["options"].keys():
			config["options"]["irc_nick_colors"] = None # use default
		self.conf = namedtuple("Conf", config_names)(**config["options"])
		#
		self.nc = NickColorizer(self.conf.irc_nick_colors)
		self.tf = TextFormattingConverter(self.conf.forward_text_formatting)

		self.irc.event_handler("connected", self.irc_connected)
		self._irc_event_handler("message", self.irc_message)
		self._irc_event_handler("action", self.irc_action)
		self.tg.event_handler("cmd_help", self.tg_help)
		self._tg_event_handler("cmd_me", self.tg_me)
		self._tg_event_handler("text", self.tg_text)
		self._tg_event_handler("media", self.tg_media)
		self._tg_event_handler("location", self.tg_location)
		self._tg_event_handler("contact", self.tg_contact)
		self._tg_event_handler("user_joined", self.tg_user_joined)
		self._tg_event_handler("user_left", self.tg_user_left)
		self._tg_event_handler("ctitle_changed", self.tg_ctitle_changed)
		self._tg_event_handler("cphoto_changed", self.tg_cphoto_changed)
		self._tg_event_handler("cphoto_deleted", self.tg_cphoto_deleted)
		self._tg_event_handler("cpinned_changed", self.tg_cpinned_changed)

	def _irc_event_handler(self, event, func):
		# So we don't have to repeat this code in every handler
		def wrap(event, *args):
			if event.channel is None:
				return
			l = self._find_link(irc=event)
			if l is None:
				logging.warning("IRC channel %s is not linked to anywhere", event.channel)
				return
			func(l, event, *args)
		self.irc.event_handler(event, wrap)

	def _tg_event_handler(self, event, func):
		# So we don't have to repeat this code in every handler
		def wrap(event, *args):
			if event.chat.type in ("private", "channel"):
				return
			l = self._find_link(tg=event)
			if l is None:
				logging.warning("Telegram chat %d is not linked to anywhere", event.chat.id)
				return
			func(l, event, *args)
		self.tg.event_handler(event, wrap)

	def _find_link(self, tg=None, irc=None):
		if tg is not None:
			for l in self.links:
				if l.telegram == tg.chat.id:
					return l
			return None
		elif irc is not None:
			for l in self.links:
				if l.irc == irc.channel:
					return l
			return None
		raise NotImplementedException()

	def _tg_format_user(self, user):
		if user.username is not None:
			return user.username
		v1 = user.first_name
		v2 = user.last_name
		return ("" if v1 is None else v1) + " " + ("" if v2 is None else v2)

	def _tg_format_msg_prefix(self, event, action=False):
		fmt = "* %s" if action else "<%s>"
		r = fmt % self.nc.colorize(self._tg_format_user(event.from_user))
		if event.forward_from is not None:
			if event.forward_from_chat is not None:
				r += " Fwd from %s in %s" % (
					self.nc.colorize(self._tg_format_user(event.forward_from)),
					event.forward_from_chat.title,
				)
			else:
				r += " Fwd from %s:" % self.nc.colorize(self._tg_format_user(event.forward_from))
		return r

	def _tg_format_msg(self, event):
		if event.reply_to_message is not None:
			pre = "@%s, " % self.nc.colorize(self._tg_format_user(event.reply_to_message.from_user))
		else:
			pre = ""
		# TODO: support non-text messages here (for pinned msgs)
		if event.content_type != "text":
			return self._tg_format_msg_prefix(event) + " " + pre + "(Media message)"
		return self._tg_format_msg_prefix(event) + " " + pre + event.text.replace("\n", " … ")


	def irc_connected(self):
		for l in self.links:
			self.irc.join(l.irc)

	def irc_message(self, l, event):
		logging.info("[IRC] %s in %s says: %s", event.nick, event.channel, event.message)
		if self.conf.telegram_bold_nicks:
			fmt = "&lt;<b>%s</b>&gt; %s"
		else:
			fmt = "&lt;%s&gt; %s"
		self.tg.send_message(l.telegram, fmt % (event.nick, self.tf.irc2html(event.message)), parse_mode="HTML")

	def irc_action(self, l, event):
		logging.info("[IRC] %s in %s does action: %s", event.nick, event.channel, event.message)
		if self.conf.telegram_bold_nicks:
			fmt = "* <b>%s</b> %s"
		else:
			fmt = "* %s %s"
		self.tg.send_message(l.telegram, fmt % (event.nick, self.tf.irc2html(event.message)), parse_mode="HTML")


	def tg_help(self, event):
		self.tg.send_reply_message(event, "pytgbridge (Telegram)")

	def tg_me(self, l, event):
		if len(event.text.split(" ")) < 2:
			return
		atext = " ".join(event.text.split(" ")[1:])
		logging.info("[TG] /me action: %s", atext)
		self.irc.privmsg(l.irc, self._tg_format_msg_prefix(event, True) + " " + atext)

	def tg_text(self, l, event):
		logging.info("[TG] text: %s", event.text)
		self.irc.privmsg(l.irc, self._tg_format_msg(event))

	def tg_media(self, l, event, media):
		logging.info("[TG] media (%s)", media.type)
		mediadesc = "(???)"
		if media.type == "audio":
			if media.desc is not None and self.conf.forward_audio_description:
				mediadesc = "(Audio, %s: %s)" % (format_audio_duration(media.duration), media.desc)
			else:
				mediadesc = "(Audio, %s)" % format_audio_duration(media.duration)
		elif media.type == "document":
			if self.conf.forward_document_mime:
				mediadesc = "(Document, %s)" % media.mime
			else:
				mediadesc = "(Document)"
		elif media.type == "photo":
			mediadesc = "(Photo, %dx%d)" % media.dimensions
		elif media.type == "sticker":
			if self.conf.forward_sticker_dimensions:
				mediadesc = "(Sticker, %dx%d)" % media.dimensions
			else:
				mediadesc = "(Sticker)"
		elif media.type == "video":
			mediadesc = "(Video, %s)" % format_audio_duration(media.duration)
		elif media.type == "voice":
			mediadesc = "(Voice, %s)" % format_audio_duration(media.duration)
		#
		url = self.web.download_and_serve(self.tg.get_file_url(media.file_id))
		post = (" " + event.caption) if event.caption is not None else ""
		self.irc.privmsg(l.irc, self._tg_format_msg_prefix(event) + " " + mediadesc + " " + url + post)

	def tg_location(self, l, event):
		logging.info("[TG] location")
		self.irc.privmsg(l.irc, "%s (Location, lat: %.4f, lon: %.4f)" % (
			self._tg_format_msg_prefix(event),
			event.location.longitude,
			event.location.latitude,
		))

	def tg_contact(self, l, event):
		logging.info("[TG] contact")
		self.irc.privmsg(l.irc, "%s (Contact, Name: %s%s, Phone: %s)" % (
			self._tg_format_msg_prefix(event),
			event.contact.first_name,
			(" " + event.contact.last_name) if event.contact.last_name is not None else "",
			event.contact.phone_number,
		))

	def tg_user_joined(self, l, event):
		logging.info("[TG] user joined: %d", event.new_chat_member.id)
		if event.from_user.id == event.new_chat_member.id:
			self.irc.privmsg(l.irc, "%s has joined" % self.nc.colorize(self._tg_format_user(event.from_user)))
		else:
			self.irc.privmsg(l.irc, "%s was added by %s" % (
				self.nc.colorize(self._tg_format_user(event.new_chat_member)),
				self.nc.colorize(self._tg_format_user(event.from_user)),
			))

	def tg_user_left(self, l, event):
		logging.info("[TG] user left: %d", event.left_chat_member.id)
		if event.from_user.id == event.left_chat_member.id:
			self.irc.privmsg(l.irc, "%s has left" % self.nc.colorize(self._tg_format_user(event.from_user)))
		else:
			self.irc.privmsg(l.irc, "%s was removed by %s" % (
				self.nc.colorize(self._tg_format_user(event.left_chat_member)),
				self.nc.colorize(self._tg_format_user(event.from_user)),
			))

	def tg_ctitle_changed(self, l, event):
		logging.info("[TG] chat title changed: %s", event.new_chat_title)
		self.irc.privmsg(l.irc, "%s set a new chat title: %s" % (
			self.nc.colorize(self._tg_format_user(event.from_user)),
			event.new_chat_title,
		))

	def tg_cphoto_changed(self, l, event, media):
		logging.info("[TG] chat photo changed")
		url = self.web.download_and_serve(self.tg.get_file_url(media.file_id))
		self.irc.privmsg(l.irc, "%s set a new chat photo (%dx%d): %s" % (
			self.nc.colorize(self._tg_format_user(event.from_user)),
			media.dimensions[0], media.dimensions[1], url
		))

	def tg_cphoto_deleted(self, l, event):
		logging.info("[TG] chat photo deleted")
		self.irc.privmsg(l.irc, "%s deleted the chat photo" % (
			self.nc.colorize(self._tg_format_user(event.from_user)),
		))

	def tg_cpinned_changed(self, l, event):
		logging.info("[TG] pinned message changed")
		self.irc.privmsg(l.irc, "%s pinned message: %s" % (
			self.nc.colorize(self._tg_format_user(event.from_user)),
			self._tg_format_msg(event.pinned_message),
		))

