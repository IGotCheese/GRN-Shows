"""Drive the running Kodi over its TCP JSON-RPC port.

The Microsoft Store build is a UWP app, so its HTTP interface is unreachable on
loopback (AppContainer blocks it). The raw TCP JSON-RPC server on 9090 is not
blocked, so that is what this uses.

    py -3 tools/kodi.py ping
    py -3 tools/kodi.py dir "plugin://plugin.video.grnshows/"
    py -3 tools/kodi.py open                 # open the add-on in the GUI
    py -3 tools/kodi.py window               # which window is on screen
    py -3 tools/kodi.py key down|select|back
"""
import json
import socket
import sys

HOST, PORT = "127.0.0.1", 9090
ADDON = "plugin.video.grnshows"


def call(method, params=None, timeout=90):
    """One request, one response. Kodi may send notifications first."""
    payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1})
    connection = socket.create_connection((HOST, PORT), timeout=timeout)
    try:
        connection.sendall(payload.encode("utf-8"))
        buffer = ""
        connection.settimeout(timeout)
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            # Kodi interleaves notifications; take the first complete object
            # that carries our id.
            decoder, index = json.JSONDecoder(), 0
            while index < len(buffer):
                try:
                    message, end = decoder.raw_decode(buffer, index)
                except ValueError:
                    break
                index = end
                while index < len(buffer) and buffer[index] in " \r\n\t":
                    index += 1
                if isinstance(message, dict) and message.get("id") == 1:
                    return message
            buffer = buffer[index:]
        return {"error": "no response"}
    finally:
        connection.close()


def listing(directory):
    result = call("Files.GetDirectory",
                  {"directory": directory, "media": "video",
                   "properties": ["title", "art", "plot"]})
    if "error" in result:
        return None, result["error"]
    files = result.get("result", {}).get("files", [])
    return files, None


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    command = argv[0]
    if command == "ping":
        print(call("JSONRPC.Ping"))
    elif command == "dir":
        files, error = listing(argv[1] if len(argv) > 1 else "plugin://%s/" % ADDON)
        if error:
            print("ERROR:", error)
            return 1
        print("%d items" % len(files))
        for item in files:
            print("  %-56s %s" % (item.get("label", "")[:56], item.get("file", "")[:70]))
    elif command == "open":
        print(call("Addons.ExecuteAddon", {"addonid": ADDON}))
    elif command == "window":
        print(call("GUI.GetProperties", {"properties": ["currentwindow", "currentcontrol", "fullscreen"]}))
    elif command == "key":
        actions = {"down": "Input.Down", "up": "Input.Up", "left": "Input.Left",
                   "right": "Input.Right", "select": "Input.Select", "back": "Input.Back",
                   "home": "Input.Home"}
        print(call(actions[argv[1]]))
    elif command == "action":
        print(call("Input.ExecuteAction", {"action": argv[1]}))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
