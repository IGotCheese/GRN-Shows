"""Example GRN Shows external source provider.

Copy this file to a folder and select that folder in add-on settings. Providers
must expose search(media) and return source dictionaries. Only return content
the user is authorized to access.
"""


def search(media):
    if media.get("media_type") == "movie" and media.get("id") == 550:
        return [{
            "name": "My server · 1080p",
            "url": "https://media.example.com/authorized/example-1080p.mp4",
            "quality": "1080p",
        }]
    return []
