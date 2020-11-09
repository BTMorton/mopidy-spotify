import logging
import pathlib
import threading

from pprint import pprint

import pykka
from mopidy import backend, httpclient, core

from mopidy_spotify import Extension, library, playback, playlists, web, api, connect

logger = logging.getLogger(__name__)


class SpotifyBackend(pykka.ThreadingActor, backend.Backend, core.CoreListener):

    def __init__(self, config, audio):
        super().__init__()

        self._config = config
        self._audio = audio
        self._actor_proxy = None
        self._event_loop = None
        self._bitrate = None
        self._api = api.SpotifyAPI(backend=self)
        self._connect = connect.SpotifyConnect(backend=self)

        self.library = library.SpotifyLibraryProvider(backend=self)
        self.playback = playback.SpotifyPlaybackProvider(
            audio=audio, backend=self
        )
        if config["spotify"]["allow_playlists"]:
            self.playlists = playlists.SpotifyPlaylistsProvider(backend=self)
        else:
            self.playlists = None
        self.uri_schemes = ["spotify"]

    def on_start(self):
        self._actor_proxy = self.actor_ref.proxy()

        self._connect.load_device_id()

    def on_stop(self):
        logger.debug("Logging out of Spotify")

    def track_playback_started(self, tl_track):
        if not self._connect.is_playing():
            return

        track_uri = ""
        if tl_track is not None:
            track_uri = tl_track.track.uri

        if not track_uri.startswith("spotify:"):
            logger.info("Stopping Spotify as we should not longer be playing")
            self._connect.pause()

    def mute_changed(self, mute):
        if not self._connect.is_active_device():
            return

        spotify_volume = self._connect.get_volume()
        current_volume = self._audio.mixer.get_volume().get()

        if (mute and spotify_volume == 0) or (not mute and spotify_volume == current_volume):
            return

        logger.info("Mute has changed to: {0}".format(mute))

        if mute:
            self._connect.set_volume(0)
        else:
            self._connect.set_volume(current_volume)

    def volume_changed(self, volume):
        if not self._connect.is_active_device():
            return

        spotify_volume = self._connect.get_volume()
        mute = self._audio.mixer.get_mute().get()

        if (mute and spotify_volume == 0) or (not mute and spotify_volume == volume):
            return

        logger.info("Volume has changed to: {0}".format(volume))

        if mute:
            self._connect.set_volume(0)
        else:
            self._connect.set_volume(volume)

