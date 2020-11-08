import logging

from mopidy import models
from pprint import pprint
import spotify
from mopidy_spotify import countries, playlists, translator
from mopidy_spotify.utils import flatten, iterate

logger = logging.getLogger(__name__)

ROOT_DIR = models.Ref.directory(uri="spotify:directory", name="Spotify")

_TOP_LIST_DIR = models.Ref.directory(uri="spotify:top", name="Top lists")
_YOUR_MUSIC_DIR = models.Ref.directory(uri="spotify:your", name="Your music")
_PLAYLISTS_DIR = models.Ref.directory(uri="spotify:playlists", name="Playlists")

_ROOT_DIR_CONTENTS = [
    _TOP_LIST_DIR,
    _YOUR_MUSIC_DIR,
    _PLAYLISTS_DIR,
]

_TOP_LIST_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:top:tracks", name="Top tracks"),
    models.Ref.directory(uri="spotify:top:artists", name="Top artists"),
]

_YOUR_MUSIC_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:your:tracks", name="Your tracks"),
    models.Ref.directory(uri="spotify:your:albums", name="Your albums"),
]

_PLAYLISTS_DIR_CONTENTS = [
    models.Ref.directory(uri="spotify:playlists:featured", name="Featured"),
]

_TOPLIST_TYPES = {
    "albums": spotify.ToplistType.ALBUMS,
    "artists": spotify.ToplistType.ARTISTS,
    "tracks": spotify.ToplistType.TRACKS,
}


def browse(*, config, api, uri):
    if uri == ROOT_DIR.uri:
        return _ROOT_DIR_CONTENTS
    elif uri == _TOP_LIST_DIR.uri:
        return _TOP_LIST_DIR_CONTENTS
    elif uri == _YOUR_MUSIC_DIR.uri:
        return _YOUR_MUSIC_DIR_CONTENTS
    elif uri == _PLAYLISTS_DIR.uri:
        return _PLAYLISTS_DIR_CONTENTS + _browse_user_playlists(api)
    elif uri.startswith("spotify:user:") or uri.startswith("spotify:playlist:"):
        return _browse_playlist(api, uri, config)
    elif uri.startswith("spotify:album:"):
        return _browse_album(api, uri, config)
    elif uri.startswith("spotify:artist:"):
        return _browse_artist(api, uri, config)
    elif uri.startswith("spotify:top:"):
        parts = uri.replace("spotify:top:", "").split(":")
        if len(parts) == 1:
            return _browse_toplist_user(api, variant=parts[0])
        else:
            logger.info(f"Failed to browse {uri!r}: Toplist URI parsing failed")
            return []
    elif uri.startswith("spotify:your:"):
        parts = uri.replace("spotify:your:", "").split(":")
        if len(parts) == 1:
            return _browse_your_music(api, variant=parts[0])
    elif uri.startswith("spotify:playlists:"):
        parts = uri.replace("spotify:playlists:", "").split(":")
        if len(parts) == 1:
            return _browse_playlists(api, variant=parts[0])

    logger.info(f"Failed to browse {uri!r}: Unknown URI type")
    return []

def _browse_user_playlists(api):
    user_playlists = flatten(
        data.get("items")
        for data in iterate(api, api.current_user_playlists())
    )

    return list(translator.to_playlist_refs(
        user_playlists, api.user_id
    ))


def _browse_playlist(api, uri, config):
    return playlists.playlist_lookup(
        api, uri, config["bitrate"], as_items=True
    )


def _browse_album(api, uri, config):
    sp_album_tracks = api.album_tracks(uri).get("items")

    return list(
        translator.web_to_track_refs(sp_album_tracks, check_playable=False)
    )


def _browse_artist(api, uri, config):
    # sp_artist_browser = api.artist(uri)
    sp_artist_top_tracks = api.artist_top_tracks(uri).get("tracks")
    sp_artist_albums = api.artist_albums(uri).get("items")

    top_tracks = list(
        translator.web_to_track_refs(sp_artist_top_tracks, check_playable=False)
    )
    albums = list(
        translator.web_to_album_refs(sp_artist_albums)
    )
    return top_tracks + albums


def _browse_toplist_user(api, variant):
    if variant in ("tracks", "artists"):
        if variant == "tracks":
            source = api.current_user_top_tracks(limit=50)
        else:
            source = api.current_user_top_artists(limit=50)

        items = flatten(
            [
                page.get("items", [])
                for page in iterate(api, source)
                if page
            ]
        )

        if variant == "tracks":
            return list(translator.web_to_track_refs(items, check_playable=False))
        else:
            return list(translator.web_to_artist_refs(items))
    else:
        return []


def _browse_your_music(api, variant):
    if variant in ("tracks", "albums"):
        if variant == "tracks":
            source = api.current_user_saved_tracks(limit=50)
        else:
            source = api.current_user_saved_albums(limit=50)
        items = flatten(
            [
                page.get("items", [])
                for page in iterate(api, source)
                if page
            ]
        )

        if variant == "tracks":
            return list(translator.web_to_track_refs(items, check_playable=False))
        else:
            return list(translator.web_to_album_refs(items))
    else:
        return []


def _browse_playlists(api, variant):
    if variant == "featured":
        items = flatten(
            [
                page.get("playlists", {}).get("items", [])
                for page in iterate(api, api.featured_playlists(limit=50))
                if page
            ]
        )
        return list(translator.to_playlist_refs(items))
    else:
        return []
