import os
import urllib
import logging
import time
import uuid
# for built-in HTTP server:
import threading
import tempfile
import http.server
import socketserver
# for WebpConverter:
import subprocess

def http_server_thread(host, port, wwwpath):
	os.chdir(wwwpath)
	serv = socketserver.TCPServer((host, port), http.server.SimpleHTTPRequestHandler)
	logging.info("Built-in HTTP server listening on %s:%d, dir: %s", host, port, wwwpath)
	serv.serve_forever()

def urlopen(url, headers={}):
	r = urllib.request.Request(url, headers=headers)
	return urllib.request.urlopen(r)

def fdcopy(fp1, fp2):
	while True:
		data = fp1.read(1024 * 1024)
		if not data:
			return
		fp2.write(data)

def download_file(url, f):
	r = urlopen(url)
	fdcopy(r, f)
	r.close()

def millitime():
	return int(time.time() * 1000)

class WebBackend():
	def __init__(self, config):
		self.type = config["type"]
		if self.type == "external":
			self.webpath = config["webpath"]
			self.baseurl = config["baseurl"]
			self.subdirs = config["use_subdirs"]
		elif self.type == "builtin":
			bind = config.get("bind", "127.0.0.1")
			port = config["port"]
			baseurl = config.get("baseurl", "http://%s:%d" % (bind, port))
			self.subdirs = config["use_subdirs"]
			# Used by download_and_serve():
			self.webpath = tempfile.mkdtemp()
			self.baseurl = baseurl
			t = threading.Thread(target=http_server_thread, args=(bind, port, self.webpath))
			t.start()
		elif self.type == "stub":
			logging.warning("Web backend not functional! (stub)")
			return
		else:
			logging.error("Unknown web backend type")
			exit(1)

		self.f_mode = config.get("filename_mode", "counter")
		if self.f_mode == "counter":
			self.f_number = 1
		elif self.f_mode in ("timestamp", "uuid"):
			pass
		else:
			logging.error("Unknown filename mode")
			exit(1)

	@staticmethod
	def _hash(s):
		v = 0
		for c in s:
			v ^= ord(c) * 37
			v = (v << 1) & 0xffff | (v >> 15) # ROR by 1 bit
		return v

	def _filepath(self, filename):
		if not self.subdirs:
			return filename
		h = WebBackend._hash(filename)
		h = chr(97 + h % 26) # A-Z
		os.makedirs(self.webpath + "/" + h, exist_ok=True)
		return h + "/" + filename

	def _filename(self, extension=None):
		suff = ("." + extension) if extension else ""
		if self.f_mode == "counter":
			self.f_number += 1
			return "file_%d%s" % (self.f_number - 1, suff)
		elif self.f_mode == "timestamp":
			return "%d%s" % (millitime(), suff)
		elif self.f_mode == "uuid":
			return "%s%s" % (uuid.uuid4(), suff)

	def download_and_serve(self, url, filename=None, extension=None, hook=None):
		if self.type == "stub":
			return "<no link available>"
		if filename is None:
			filename = self._filename(extension)
		else:
			assert(extension is None)

		filepath = self._filepath(filename)
		with open(self.webpath + "/" + filepath, "wb") as f:
			download_file(url, f)

		if hook is not None:
			filepath = hook(filepath, self.webpath)
		return self.baseurl + "/" + filepath

class WebpConverter():
	@staticmethod
	def check():
		try:
			subprocess.check_call(["dwebp", "-version"], stdout=subprocess.DEVNULL)
		except:
			logging.error("The WebP command line tools need to be installed to use this feature (try: apt install webp)")
			os._exit(1)
	@staticmethod
	def hook(filepath, basedir):
		if not filepath.endswith(".webp"):
			return
		newpath = filepath[:-4] + "png"
		subprocess.check_call(["dwebp", basedir + "/" + filepath, "-o", basedir + "/" + newpath], stderr=subprocess.DEVNULL)
		os.remove(basedir + "/" + filepath)
		return newpath
