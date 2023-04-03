import telebot
import logging
import time

mapped_content_type = {
	"text": "text",
	"location": "location",
	"venue": "venue",
	"contact": "contact",
	"game": "game",
	"poll": "poll",
	"new_chat_members": "users_joined",
	"left_chat_member": "user_left",
	"new_chat_title": "ctitle_changed",
	"delete_chat_photo": "cphoto_deleted",
	"group_chat_created": "", # can't occur because we're a bot
	"supergroup_chat_created": "", # can't occur because we're a bot
	"channel_chat_created": "", # can't occur because we're a bot
	"migrate_to_chat_id": "",
	"migrate_from_chat_id": "",
	"pinned_message": "cpinned_changed",
}

content_types_media = [
	"audio",
	"animation",
	"document",
	"photo",
	"sticker",
	"video",
	"video_note",
	"voice",
]

mime_mapping = { # mime type -> file extension
	"audio/ogg": "ogg",
	"audio/x-vorbis+ogg": "ogg",
	"audio/x-opus+ogg": "ogg",
	"audio/mp4": "m4a",
	"audio/m4a": "m4a",
	"audio/mpeg": "mp3",
	"audio/mp3": "mp3",
	"audio/flac": "flac",

	"video/mp4": "mp4",
	"video/webm": "webm",

	"image/jpg": "jpg",
	"image/webp": "webp",
}

class TelegramMediaContainer():
	def __init__(self, orig, init_from="event"):
		if init_from == "photo_list":
			self.type = "photo"
			c = sorted(orig, key=lambda e: e.width*e.height, reverse=True)[0]
			self.dimensions = (c.width, c.height)
			self.file_id = c.file_id
			self.file_size = c.file_size
			self.extension = mime_mapping["image/jpg"]
			return
		elif init_from == "event":
			pass # see below
		else:
			raise NotImplementedError("???")

		self.type = orig.content_type
		mime = None
		if self.type == "audio":
			c = orig.audio
			self.mime = c.mime_type
			self.duration = c.duration
			if c.performer is None and c.title is None:
				self.desc = None
			elif c.performer is None or c.title is None:
				self.desc = (c.performer or "") + (c.title or "")
			else:
				self.desc = "%s – %s" % (c.performer, c.title)
			mime = c.mime_type
		elif self.type == "animation":
			c = orig.animation
			self.mime = c.mime_type
			self.filename = c.file_name
		elif self.type == "document":
			c = orig.document
			self.mime = c.mime_type
			self.filename = c.file_name
		elif self.type == "photo":
			c = sorted(orig.photo, key=lambda e: e.width*e.height, reverse=True)[0]
			self.dimensions = (c.width, c.height)
			mime = "image/jpg"
		elif self.type == "sticker":
			c = orig.sticker
			self.emoji = c.emoji
			self.dimensions = (c.width, c.height)
			self.is_animated = c.is_animated
			mime = "image/webp"
		elif self.type == "video":
			c = orig.video
			self.duration = c.duration
			self.dimensions = (c.width, c.height)
			mime = c.mime_type
		elif self.type == "video_note":
			c = orig.video_note
			self.duration = c.duration
			self.dimensions = c.length
			mime = "video/mp4" # no specified mime because ????
		elif self.type == "voice":
			c = orig.voice
			self.duration = c.duration
			self.mime = mime = c.mime_type
		else:
			raise NotImplementedError("content type not supported")

		self.file_id = c.file_id
		self.file_size = c.file_size
		self.extension = mime_mapping.get(mime, "bin") if mime is not None else None
		if self.extension == "bin":
			logging.warning("MIME type '%s' wasn't found in mapping", mime)

class TelegramClient():
	def __init__(self, config):
		if config["token"] == "":
			logging.error("No telegram token specified, exiting")
			exit(1)
		self.token = config["token"]
		self.bot = telebot.TeleBot(self.token, threaded=False)
		self.event_handlers = {}
		self.own_user = None

		self._telebot_event_handler(self.cmd_start, commands=["start"])
		self._telebot_event_handler(self.cmd_help, commands=["help"])
		self._telebot_event_handler(self.cmd_me, commands=["me"])
		for k, v in mapped_content_type.items():
			if v == "": continue
			self._telebot_event_handler_passthrough(v, content_types=[k])
		for k in content_types_media:
			self._telebot_event_handler(self.on_media, content_types=[k])
		self._telebot_event_handler(self.on_new_chat_photo, content_types=["new_chat_photo"])

	def run(self):
		self.own_user = self.bot.get_me()
		logging.info("Polling for Telegram events")
		while True:
			try:
				self.bot.polling(none_stop=True)
			except Exception as e:
				# you're not supposed to call .polling() more than once but i'm left with no choice
				logging.warning("%s while polling Telegram, retrying", type(e).__name__)
				time.sleep(1)

	def event_handler(self, name, func):
		self.event_handlers[name] = func


	def _invoke_event_handler(self, name, args=(), kwargs={}):
		if name not in self.event_handlers.keys():
			logging.warning("Unhandeled '%s' event", name)
			return
		try:
			self.event_handlers[name](*args, **kwargs)
		except Exception as e:
			logging.exception("Exception in Telegram event handler")

	def _telebot_event_handler(self, _func, **kwargs):
		self.bot.message_handler(**kwargs)(_func)

	def _telebot_event_handler_passthrough(self, evname, **kwargs):
		def h(message):
			self._invoke_event_handler(evname, (message, ))
		self._telebot_event_handler(h, **kwargs)

	def _is_our_cmd(self, message):
		# workaround because pyTelegramBotAPI is missing this
		cmd = message.text.split(" ")[0]
		if "@" in cmd:
			botname = cmd.split("@")[1]
			return botname == self.own_user.username
		else:
			return message.chat.type == "private"


	def cmd_start(self, message):
		if not self._is_our_cmd(message):
			return
		self._invoke_event_handler("cmd_start", (message, ))

	def cmd_help(self, message):
		if not self._is_our_cmd(message):
			return
		self._invoke_event_handler("cmd_help", (message, ))

	def cmd_me(self, message):
		self._invoke_event_handler("cmd_me", (message, ))

	def on_media(self, message):
		# TODO: remove when pyTelegramBotAPI supports this:
		setattr(message, "via_bot", telebot.types.User.de_json(message.json.get("via_bot")))
		self._invoke_event_handler("media", (message, TelegramMediaContainer(message)))

	def on_new_chat_photo(self, message):
		media = TelegramMediaContainer(message.new_chat_photo, init_from="photo_list")
		self._invoke_event_handler("cphoto_changed", (message, media))


	def send_message(self, chat_id, text, **kwargs):
		self.bot.send_message(chat_id, text, **kwargs)

	def send_reply_message(self, event, text, **kwargs):
		self.bot.send_message(event.chat.id, text, reply_to_message_id=event.message_id)

	def get_file_url(self, file_id, allowed_failure=False):
		try:
			info = self.bot.get_file(file_id)
		except telebot.apihelper.ApiException as e:
			if not allowed_failure:
				logging.exception("Retrieving file info failed")
			return None
		return "https://api.telegram.org/file/bot%s/%s" % (self.token, info.file_path)

	def get_own_user(self):
		return self.own_user
