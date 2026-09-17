"""Walk the published repository exactly as Kodi does.

Skipped unless GRN_REPO_URL is set, so the offline suite stays offline:

    GRN_REPO_URL=http://167.114.157.225:8087 py -3 -m unittest tests.test_live_repository -v

This exists because every earlier check confirmed that individual URLs return
200, which is not the same thing as the install working. Kodi browses
directories, and the directory listings were returning 403 while every file
was fine.
"""
import hashlib
import io
import os
import re
import unittest
import xml.etree.ElementTree as ET
from urllib.request import urlopen
from zipfile import ZipFile

BASE = (os.environ.get("GRN_REPO_URL") or "").rstrip("/")


def get(url):
    with urlopen(url, timeout=30) as response:
        return response.status, response.read()


@unittest.skipUnless(BASE, "set GRN_REPO_URL to run the live repository walk")
class LiveRepositoryTests(unittest.TestCase):
    def test_kodi_can_browse_and_install(self):
        # 1. Add source, then Install from zip file: Kodi lists the source root.
        status, body = get(BASE + "/")
        self.assertEqual(status, 200)
        listing = body.decode("utf-8", "replace")
        hrefs = re.findall(r'href="([^"]+)"', listing)
        self.assertTrue(any(h.endswith(".zip") for h in hrefs),
                        "the source root shows no ZIP, so Kodi shows an empty source")

        # 2. The repository ZIP is the one the guide tells people to click.
        repo_name = next(h for h in hrefs if h.startswith("repository.grnshows") and h.endswith(".zip"))
        status, repo_zip = get(BASE + "/" + repo_name)
        self.assertEqual(status, 200)
        with ZipFile(io.BytesIO(repo_zip)) as archive:
            self.assertIsNone(archive.testzip())
            manifest = ET.fromstring(archive.read("repository.grnshows/addon.xml"))

        # 3. Kodi reads the repository's own addon.xml for where to look next.
        directory = manifest.find("./extension/dir")
        info_url = directory.find("info").text
        checksum_url = directory.find("checksum").text
        datadir = directory.find("datadir").text

        # 4. It fetches addons.xml and verifies it against the published md5.
        status, addons_xml = get(info_url)
        self.assertEqual(status, 200)
        status, checksum = get(checksum_url)
        self.assertEqual(status, 200)
        self.assertEqual(hashlib.md5(addons_xml).hexdigest(), checksum.decode().strip(),
                         "addons.xml does not match addons.xml.md5, Kodi refuses the repository")

        # 5. It resolves the add-on version and downloads it from datadir.
        index = ET.fromstring(addons_xml)
        addon = index.find("./addon[@id='plugin.video.grnshows']")
        self.assertIsNotNone(addon, "the repository does not advertise the add-on")
        version = addon.attrib["version"]
        addon_url = "%s/plugin.video.grnshows/plugin.video.grnshows-%s.zip" % (datadir.rstrip("/"), version)
        status, addon_zip = get(addon_url)
        self.assertEqual(status, 200)

        # 6. The downloaded add-on has to be installable and carry its keys.
        with ZipFile(io.BytesIO(addon_zip)) as archive:
            self.assertIsNone(archive.testzip())
            names = archive.namelist()
            self.assertIn("plugin.video.grnshows/addon.xml", names)
            self.assertIn("plugin.video.grnshows/resources/lib/grnshows.py", names)
            self.assertIn("plugin.video.grnshows/resources/lib/service.py", names)
            packaged = ET.fromstring(archive.read("plugin.video.grnshows/addon.xml"))
            self.assertEqual(packaged.attrib["version"], version,
                             "addons.xml advertises a version the ZIP does not contain")
            registry = archive.read("plugin.video.grnshows/resources/lib/caches/settings_cache.py").decode()
        for setting_id, label in (("tmdb_api", "TMDb key"), ("trakt.client", "Trakt application"),
                                  ("trakt.secret", "Trakt secret")):
            self.assertNotIn("{'setting_id': '%s', 'setting_type': 'string', 'setting_default': ''}" % setting_id,
                             registry, "published build ships no %s" % label)

    def test_every_advertised_addon_is_downloadable(self):
        status, addons_xml = get(BASE + "/addons.xml")
        self.assertEqual(status, 200)
        for addon in ET.fromstring(addons_xml):
            addon_id, version = addon.attrib["id"], addon.attrib["version"]
            url = "%s/zips/%s/%s-%s.zip" % (BASE, addon_id, addon_id, version)
            status, payload = get(url)
            self.assertEqual(status, 200, "%s is advertised but not downloadable" % addon_id)
            with ZipFile(io.BytesIO(payload)) as archive:
                self.assertIsNone(archive.testzip())

    def test_directories_are_browsable(self):
        for path in ("/", "/zips/", "/zips/plugin.video.grnshows/", "/zips/repository.grnshows/"):
            status, _ = get(BASE + path)
            self.assertEqual(status, 200, "%s is not browsable, Kodi cannot walk the source" % path)


if __name__ == "__main__":
    unittest.main()
