import os
import urllib
import logging
# for built-in HTTP server:
import threading
import tempfile
import http.server
import socketserver

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

class WebBackend():
	def __init__(self, config):
		self.type = config["type"]
		if self.type == "external":
			self.webpath = config["webpath"]
			self.baseurl = config["baseurl"]
			self.subdirs = config["use_subdirs"]
		elif self.type == "builtin":
			bind = "127.0.0.1" if "bind" not in config else config["bind"]
			port = config["port"]
			self.subdirs = config["use_subdirs"]
			# Used by download_and_serve():
			self.webpath = tempfile.mkdtemp()
			self.baseurl = "http://%s:%d" % (bind, port)
			t = threading.Thread(target=http_server_thread, args=(bind, port, self.webpath))
			t.start()
		elif self.type == "stub":
			logging.warning("Web backend not functional! (stub)")
		else:
			logging.error("Unknown web backend type")
			exit(1)

	@staticmethod
	def _hash(s):
		v = 0
		for c in s:
			v += ord(c)
			v = (v << 1) & 0xffff | (v >> 15) # ROR by 1 bit
		return v

	def _filepath(self, filename):
		assert(self.type in ("external", "builtin"))
		if not self.subdirs:
			return filename
		h = WebBackend._hash(filename)
		h = chr(97 + h % 26) # A-Z
		try:
			os.mkdir(self.webpath + "/" + h)
		except FileExistsError:
			pass
		return h + "/" + filename

	def download_and_serve(self, url, filename=None):
		if self.type == "stub":
			return "<no link available>"
		filepath = self._filepath(url.split("/")[-1] if filename is None else filename)
		with open(self.webpath + "/" + filepath, "wb") as f:
			download_file(url, f)
		return self.baseurl + "/" + filepath

