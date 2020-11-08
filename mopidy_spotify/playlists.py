import logging

from mopidy import backend

import spotify
from mopidy_spotify import translator, utils
from pprint import pprint

logger = logging.getLogger(__name__)


class SpotifyPlaylistsProvider(backend.PlaylistsProvider):
    def __init__(self, backend):
        self._backend = backend
        self._timeout = self._backend._config["spotify"]["timeout"]

    def as_list(self):
        return list(self._get_flattened_playlist_refs())

    def _get_flattened_playlist_refs(self):
        api = self._backend._api.get_client()
        user_playlists = utils.flatten(
            data.get("items")
            for data in utils.iterate(api, api.current_user_playlists())
        )

        return translator.to_playlist_refs(
            user_playlists, api.user_id
        )

    def get_items(self, uri):
        with utils.time_logger(f"playlist.get_items({uri!r})", logging.DEBUG):
            return self._get_playlist(uri, as_items=True)

    def lookup(self, uri):
        with utils.time_logger(f"playlists.lookup({uri!r})", logging.DEBUG):
            return self._get_playlist(uri)

    def _get_playlist(self, uri, as_items=False):
        return playlist_lookup(
            self._backend._api.get_client(),
            uri,
            self._backend._bitrate,
            as_items,
        )

    def create(self, name):
        pass  # TODO

    def delete(self, uri):
        pass  # TODO

    def save(self, playlist):
        pass  # TODO


def playlist_lookup(api, uri, bitrate, as_items=False):
    logger.debug(f'Fetching Spotify playlist "{uri!r}"')
    web_playlist = api.playlist(uri)

    if web_playlist == {}:
        logger.error(f"Failed to lookup Spotify playlist URI {uri!r}")
        return

    playlist = translator.to_playlist(
        web_playlist,
        username=api.user_id,
        bitrate=bitrate,
        as_items=as_items,
    )

    if playlist is None:
        return

    return playlist
