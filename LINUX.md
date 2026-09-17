# GRN Shows on Linux

GRN Shows is our own project. The current application runs inside Kodi; the
repository server distributes installations and updates. Linux can run either
or both. This is not yet a standalone desktop or browser media player.

## Build and host

Requires Python 3.8 or newer. Copy this project to your Linux server, for example
`/srv/grn-shows`, then use the address your Kodi devices can reach:

```sh
cd /srv/grn-shows
python3 build.py --base-url http://192.168.1.50:8080
python3 serve.py --bind 0.0.0.0 --port 8080
```

Replace `192.168.1.50` with your server address. Add that URL in Kodi File Manager,
install the repository ZIP, and select GRN Shows from Install from repository.
The foreground server stops with Ctrl+C. It serves only `dist/`.

For persistent hosting, serve `dist/` through the existing Linux web server.
`deploy/nginx.conf` provides a site template on port 8080. Adjust its root and
server name before installing it, then validate the existing Nginx configuration
with `sudo nginx -t` before reloading it. For HTTPS hosting, use your server's
existing TLS/reverse-proxy configuration and build with the final HTTPS URL.
Do not use localhost in a repository intended for other devices.

Builds preserve older versioned ZIPs. Bump the add-on manifest version when
publishing updates, rebuild with the same base URL, and publish the new files.
For public hosting, upload ZIPs before publishing the index and checksum.

## Kodi running on Linux

Install the same add-on ZIP through Kodi. Kodi supplies the Python runtime and
`xbmc` modules; running `default.py` directly in a shell will not work. Configure
TMDb, Real-Debrid, and Trakt in Kodi as described in README.md.
Use Linux paths for personal JSON and provider folders. Account tokens belong
to the Kodi client and are not part of the repository server.

## Verification

```sh
python3 -m unittest discover -s tests -v
curl -I http://192.168.1.50:8080/addons.xml
```

The repository is deployed on `playgrn` (AlmaLinux 10.2) at
http://167.114.157.225:8087/. See [deployment notes](deploy/ALMALINUX.md).
All 12 tests passed on that host. Live Kodi authorization and playback still
require testing with your accounts.
