import logging

from mopidy_spotify import playlists, translator, utils, web
from pprint import pprint

logger = logging.getLogger(__name__)

_VARIOUS_ARTISTS_URIS = [
    "spotify:artist:0LyfQWJT6nXafLPZqxe9Of",
]


def lookup(config, api, uri):
    try:
        web_link = web.WebLink.from_uri(uri)
    except ValueError as exc:
        logger.debug(f"Failed to lookup {uri!r}: {exc}")
        return []

    if web_link.type == web.LinkType.PLAYLIST:
        return _lookup_playlist(config, api, uri)
    elif web_link.type is web.LinkType.TRACK:
        return list(_lookup_track(config, api, uri))
    elif web_link.type is web.LinkType.ALBUM:
        return list(_lookup_album(config, api, uri))
    elif web_link.type is web.LinkType.ARTIST:
        with utils.time_logger("Artist lookup"):
            return list(_lookup_artist(config, api, uri))
    else:
        logger.info(
            f"Failed to lookup {uri!r}: Cannot handle {web_link.type!r}"
        )
        return []


def _lookup_track(config, api, uri):
    (track_uri, context_uri) = translator.get_context_from_track_uri(uri)
    sp_track = api.track(track_uri)

    track = translator.web_to_track(
        sp_track, bitrate=config["bitrate"], context_uri=context_uri)

    if track is not None:
        yield track


def _lookup_album(config, api, uri):
    sp_album_tracks = api.album_tracks(uri, market="from_token")["items"]
    for sp_track in sp_album_tracks:
        track = translator.web_to_track(
            sp_track, bitrate=config["bitrate"], context_uri=uri)
        if track is not None:
            yield track


def _lookup_artist(config, api, uri):
    sp_artist_albums = api.artist_albums(
        uri, country=config["country"])["items"]

    sp_album_tracks = []
    for sp_album in sp_artist_albums:
        if sp_album["album_type"] == "compilation":
            continue
        yield from _lookup_album(config, api, sp_album["uri"])


def _lookup_playlist(config, api, uri):
    playlist = playlists.playlist_lookup(
        api, uri, config["bitrate"]
    )
    if playlist is None:
        raise Exception("Playlist Web API lookup failed")
    return playlist.tracks
