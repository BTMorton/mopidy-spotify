import logging
import pathlib
import threading

from pprint import pprint

import pykka
from mopidy import httpclient, core

from mopidy_spotify import Extension, library, playback, playlists, web, api, connect

logger = logging.getLogger(__name__)


class SpotifyFrontend(pykka.ThreadingActor, core.CoreListener):

    def __init__(self, config, core):
        super().__init__()

        self._config = config
        self._core = core
        self._actor_proxy = None
        self._api = api.SpotifyAPI(config=config)
        self._connect = connect.SpotifyConnect(api=self._api, config=config)

        self.uri_schemes = ["spotify"]

    def on_start(self):
        self._actor_proxy = self.actor_ref.proxy()

        self._connect.load_device_id()

    def on_stop(self):
        logger.debug("Logging out of Spotify")

    def options_changed(self):
        if not self._connect.is_active_device():
            return

        logger.debug("Handling options change")

        shuffle = self._core.tracklist.get_random().get()
        repeat = self._core.tracklist.get_repeat().get()
        repeat_one = repeat and self._core.tracklist.get_single().get()

        repeat_state = "track" if repeat_one else "context" if repeat else "off"

        client = self._api.get_client()
        playback = client.current_playback(market="from_token")

        if playback["shuffle_state"] != shuffle:
            logger.debug("Updating Spotify shuffle state to {0} from {1}".format(
                shuffle, playback["shuffle_state"]))
            client.shuffle(shuffle)

        if playback["repeat_state"] != repeat_state:
            logger.debug("Updating Spotify repeat state to {0} from {1}".format(
                repeat_state, playback["repeat_state"]))
            client.repeat(repeat_state)



