import logging
import json5
import threading
import os
import sys
import getopt

from .telegram import TelegramClient
from .irc import IRCClient
from .bridge import Bridge
from .web_backend import WebBackend

opts = {}

def start_new_thread(func, join=False, args=(), kwargs=None):
	t = threading.Thread(target=func, args=args, kwargs=kwargs)
	t.start()
	if join:
		t.join()

def readopt(name):
	for e in opts:
		if e[0] == name:
			return e[1]
	return None

def parse_config(path):
	with open(path, "rb") as f:
		s = f.read()
	try:
		return json5.loads(s)
	except ValueError as e:
		logging.error("Failed to parse configuration file:\n%s", e)
		exit(1)

def usage():
	print("Usage: %s [-q] [-c file] [-D]" % sys.argv[0])
	print("Options:")
	print("  -q    Be quieter, raise log level to WARNING")
	print("  -c    Set location of config file (default: ./config.json)")
	print("  -D    Fork into background")

def main():
	global opts
	try:
		opts, args = getopt.getopt(sys.argv[1:], "hqc:D", ["help"])
	except getopt.GetoptError as e:
		print(str(e))
		exit(1)
	# Process command line args
	if len(args) > 0 or readopt("-h") is not None or readopt("--help") is not None:
		usage()
		exit(0)
	loglevel = logging.INFO if readopt("-q") is None else logging.WARNING
	configpath = readopt("-c") or "./config.json"
	# Fork into background
	if readopt("-D") is not None and os.fork():
		sys.exit()

	logging.basicConfig(format="[%(asctime)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=loglevel)

	config = parse_config(configpath)

	logging.info("Starting up...")
	try:
		tg = TelegramClient(config["telegram"])
		irc = IRCClient(config["irc"])
		wb = WebBackend(config["web_backend"])
		b = Bridge(tg, irc, wb, config["bridge"])
	except (KeyError, TypeError):
		logging.exception("")
		logging.error("Your pytgbridge configuration is incomplete or invalid.\n"+
			"The stacktrace usually contains a hint at whats wrong.")
		os._exit(1)

	start_new_thread(tg.run)

	try:
		start_new_thread(irc.run, join=True)
	except KeyboardInterrupt:
		logging.info("Interrupted, exiting")
		os._exit(1)

if __name__ == "__main__":
	main()
