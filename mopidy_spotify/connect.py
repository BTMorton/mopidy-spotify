from pprint import pprint
from . import translator


class SpotifyConnect:
    def __init__(self, backend):
        self._backend = backend
        self._api = backend._api
        self._device_name = self._backend._config["spotify"]["device_name"]
        self._device_id = None
        self._current_uri = None

    def load_device_id(self):
        devices = self._api.get_client().devices()

        currentDevice = next((
            device
            for device in devices["devices"]
            if device["name"] == self._device_name
        ))

        if currentDevice == None:
            return

        self._device_id = currentDevice["id"]

    def is_active_device(self):
        devices = self._api.get_client().devices()

        activeDevice = next((
            device
            for device in devices["devices"]
            if device["is_active"]
        ))

        if activeDevice is None:
            return False

        return activeDevice["id"] == self._device_id

    def is_playing(self):
        playback = self.current_playback()

        return playback is not None

    def current_playback(self):
        if self._device_id is None:
            return None

        playback = self._api.get_client().current_playback()
        if playback is None or playback["device"] is None:
            return None
        if playback["device"]["id"] != self._device_id:
            return None

        if playback["is_playing"]:
            self._current_uri = playback["item"]["uri"]

        return playback

    def current_track(self):
        playback = self.current_playback()

        if playback is None or playback["item"] is None:
            return None

        return translator.web_to_track(playback["item"])

    def play(self, uri=None):
        playback = self.current_playback()

        if playback is not None:
            # if we're already playing the target track, can skip
            if uri is not None and self._current_uri == uri:
                return
            # if we're already playing and don't have a target track, can skip
            if uri is None and playback["is_playing"]:
                return

        # if we don't have a target track, just start playing here
        if uri is None:
            self._api.get_client().transfer_playback(
                device_id=self._device_id, force_play=True)
        # otherwise, start playing the target track on this device
        else:
            self._api.get_client().start_playback(
                device_id=self._device_id, uris=[uri])

    def pause(self):
        playback = self.current_playback()

        # only send a pause command when we're actually playing on this device
        if playback is not None:
            self._api.get_client().pause_playback()

    def seek(self, time_position):
        playback = self.current_playback()

        # only try to seek when we're actually playing on this device
        if playback is not None:
            self._api.get_client().seek_track(time_position)

    def get_current_time(self):
        playback = self.current_playback()

        if playback is None:
            return 0

        return playback["progress_ms"]

    def get_volume(self):
        playback = self.current_playback()

        if playback is None:
            return None

        return playback["device"]["volume_percent"]

    def set_volume(self, volume):
        if not self.is_active_device():
            return

        self._api.get_client().volume(volume_percent=volume)


