import logging

from mopidy import audio, backend
from .connect import SpotifyConnect
from pprint import pprint

logger = logging.getLogger(__name__)

# These GStreamer caps matches the audio data provided by libspotify
GST_CAPS = "audio/x-raw,format=S16LE,rate=44100,channels=2,layout=interleaved"

# Extra log level with lower importance than DEBUG=10 for noisy debug logging
TRACE_LOG_LEVEL = 5


class SpotifyPlaybackProvider(backend.PlaybackProvider):
    def __init__(self, audio, backend):
        super().__init__(audio, backend)
        self._connect = backend._connect
        self._device_name = self.backend._config["spotify"]["device_name"]

        self._first_seek = False

        self._device_id = None

    def prepare_change(self):
        pass

    # def _connect_events(self):
    #     if not self._events_connected:
    #         self._events_connected = True
    #         self.backend._session.on(
    #             spotify.SessionEvent.MUSIC_DELIVERY,
    #             music_delivery_callback,
    #             self.audio,
    #             self._seeking_event,
    #             self._push_audio_data_event,
    #             self._buffer_timestamp,
    #         )
    #         self.backend._session.on(
    #             spotify.SessionEvent.END_OF_TRACK,
    #             end_of_track_callback,
    #             self._end_of_track_event,
    #             self.audio,
    #         )

    def change_track(self, track):
        if track.uri is None:
            return False

        self.audio.stop_playback()

        logger.debug(
            "Audio requested change of track; "
            "loading and starting Spotify player"
        )
        self._connect.play(track.uri)
        self.audio.set_metadata(self._connect.current_track())
        return True

    def play(self):
        logger.debug("Audio requested play; starting Spotify player")
        self._connect.play()
        return True

    def resume(self):
        logger.debug("Audio requested resume; starting Spotify player")
        self._connect.play()
        return True

    def stop(self):
        logger.debug("Audio requested stop; pausing Spotify player")
        self._connect.pause()
        return True

    def pause(self):
        logger.debug("Audio requested pause; pausing Spotify player")
        self._connect.pause()
        return True

    def seek(self, time_position):
        logger.debug(f"Audio requested seek to {time_position}")

        if time_position == 0 and self._first_seek:
            self._first_seek = False
            logger.debug("Skipping seek due to issue mopidy/mopidy#300")
            return

        self._connect.seek(time_position)
        return True

    def get_time_position(self):
        return self._connect.get_current_time()
