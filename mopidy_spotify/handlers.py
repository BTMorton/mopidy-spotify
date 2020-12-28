import json
import time
import tornado.ioloop
import logging

from pykka.messages import ProxyCall

from mopidy.core import PlaybackState, CoreListener
from mopidy.audio import AudioListener
from . import api, translator

from pprint import pprint

logger = logging.getLogger(__name__)


class LibrespotHttpHandler(tornado.web.RequestHandler):
    last_update = (None, None)

    def set_default_headers(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header(
            "Access-Control-Allow-Headers",
            (
                "Origin, X-Requested-With, Content-Type, Accept, "
                "Authorization, Client-Security-Token, Accept-Encoding"
            ),
        )

    def initialize(self, core, config):
        self.core = core
        self.config = config
        self.api = api.SpotifyAPI(config=config)
        self.ioloop = tornado.ioloop.IOLoop.current()

    # Options request
    # This is a preflight request for CORS requests
    def options(self, slug=None):
        self.set_status(204)
        self.finish()

    async def post(self, slug=None):
        id = int(time.time())

        try:
            params = json.loads(self.request.body.decode("utf-8"))
        except BaseException as ex:
            pprint(ex)
            self.handle_result(
                id=id,
                error={"code": 32700, "message": "Missing or invalid payload"},
            )
            return

        # make sure the method exists
        if valid_librespot_update(params):
            event = params["event"]
            track_uri = "spotify:track:" + params["trackID"]

            if LibrespotHttpHandler.last_update == (event, track_uri):
                logger.info(
                    "Skipping update as it's the same as the previous update")
                self.handle_result(
                    id=id,
                    response={"message": "Librespot update handled"},
                )
                return

            LibrespotHttpHandler.last_update = (event, track_uri)

            if event != "stop" and (event != "volume_set" or await self.is_active()):
                await self.update_options_state()

            # if it's a start event, stop whatever is playing
            if event == "start":
                logger.info("Librespot has started. Stopping other playback")
                await self.core.playback.stop()

                # this will cause Spotify's volume to be updated to match that of mopidy
                CoreListener.send(
                    "volume_changed",
                    volume=(await self.core.mixer.get_volume())
                )
            # if it's a stop event, check if we're active and stop
            elif event == "stop":
                current_state = await self.core.playback.get_state()

                if current_state != PlaybackState.STOPPED and await self.is_active():
                    logger.info("Librespot has stopped. Cleaning up")
                    await self.core.playback.stop()
                    AudioListener.send("reached_end_of_stream")
            # on a change event, just trigger a track change
            elif event == "change":
                logger.info("Librespot has changed to a new track")
                await self.change_track(track_uri)
            # if we're playing, there are options
            elif event == "playing":
                current_state = await self.core.playback.get_state()
                active = await self.is_active()
                correct_track = (await self.get_current_track_uri()).startswith(track_uri)
                logger.info("Received a play update from librespot")

                # if we're already playing this track, this is most likely just a seek event
                if not active or not correct_track or current_state == PlaybackState.STOPPED:
                    logger.info("Updating current track")
                    await self.change_track(track_uri)
                elif correct_track and current_state == PlaybackState.PAUSED:
                    logger.info("Resuming playback of current track")
                    await self.core.playback.resume()

                # we may get two seek events...
                # this is needed when mopidy does the seek
                AudioListener.send(
                    "position_changed",
                    position=params["positionMS"]
                )
                # this is needed when spotify does the seek
                CoreListener.send(
                    "seeked",
                    time_position=params["positionMS"]
                )
            # a pause also has options
            elif event == "paused":
                current_state = await self.core.playback.get_state()
                current_tl_track = await self.core.playback.get_current_tl_track()
                next_track = await self.core.tracklist.eot_track(current_tl_track)

                current_track = getattr(current_tl_track, "track", None)
                current_track_uri = getattr(current_track, "uri", "")

                position_ms = params["positionMS"]

                # if there is another source active, do nothing
                if not current_track_uri.startswith("spotify:"):
                    logger.debug(
                        "Received a pause event when Spotify is not playing")
                    None
                # if we're part-way through a track, this is a user pause
                elif position_ms > 0:
                    logger.info("Received pause from librespot")
                    await self.pause(position_ms)
                # if the current state is paused, this is librespot responding to the pause action
                elif current_state == PlaybackState.PAUSED:
                    logger.info("Handling modpidy pause event")
                    await self.trigger_pause(position_ms)
                # if there is no next track scheduled, we're at the end of the playlist, so pause
                elif next_track is None:
                    logger.info("Reached end of playlist, pausing")
                    await self.pause(position_ms)
                # otherwise, we've hit the end of the track, so we need mopidy to schedule the next one
                else:
                    logger.info(
                        "Reached end of playback, scheduling next track")
                    self.core.actor_ref.ask(
                        ProxyCall(
                            attr_path=["playback", "_on_about_to_finish"],
                            args=[],
                            kwargs={},
                        )
                    )
            # on a volume event, treat volume 0 as mute and otherwise set the volume
            elif event == "volume_set":
                volume = params["volume"]
                logger.info("Received volume update to {0}".format(volume))

                muted = await self.core.mixer.get_mute()
                current_volume = await self.core.mixer.get_volume()

                if volume > 0 and current_volume != volume:
                    await self.core.mixer.set_volume(volume)

                if muted and volume > 0:
                    await self.core.mixer.set_mute(False)
                elif not muted and volume == 0:
                    await self.core.mixer.set_mute(True)

            self.handle_result(
                id=id,
                response={"message": "Librespot update handled"},
            )

        else:
            self.handle_result(
                id=id,
                error={"code": 32601, "message": "Invalid JSON payload"},
            )
            return

    # this is a helper method to lookup the uri of the current track
    async def get_current_track_uri(self):
        return getattr(await self.core.playback.get_current_track(), "uri", "")

    async def is_active(self):
        return (await self.get_current_track_uri()).startswith("spotify:")

    async def is_track_playing(self, track_uri):
        return (await self.get_current_track_uri()).startswith(track_uri)

    # update mopidy that a track change has occured
    async def change_track(self, uri):
        # if something else was playing, stop it
        if not self.is_active():
            await self.core.playback.stop()

        # get the track list entry and play it
        context_uri = None
        playback = self.api.get_client().current_playback()
        if playback is not None and playback["context"] is not None:
            context_uri = playback["context"]["uri"]

        tl_track = await self.ensure_track_in_tracklist(uri, context_uri)
        await self.core.playback.play(tlid=tl_track.tlid)

        # simulate the gstreamer playing event
        AudioListener.send(
            "stream_changed",
            uri=uri
        )

    # this is a full pause, stopping any playback and notifying the pause event
    async def pause(self, position_ms):
        await self.core.playback.pause()
        await self.trigger_pause(position_ms)

    # this is just a notification of the pause event
    async def trigger_pause(self, position_ms):
        CoreListener.send(
            "seeked",
            time_position=position_ms
        )

        await self.core.playback.set_state(PlaybackState.PAUSED)

    # this either gets the track from the track list or adds the track to it so we can play it
    async def ensure_track_in_tracklist(self, uri, context_uri=None):
        tl_tracks = await self.core.tracklist.get_tl_tracks()
        tl_track = next(
            (tl_track for tl_track in tl_tracks if tl_track.track.uri.startswith(uri)), False)

        if tl_track:
            return tl_track

        if context_uri is None:
            tl_tracks = await self.core.tracklist.add(uris=[uri])
            return tl_tracks[0]

        tracks = await self.core.library.lookup([context_uri])
        tl_tracks = await self.core.tracklist.add(tracks=tracks[context_uri])
        return next((tl_track for tl_track in tl_tracks if tl_track.track.uri.startswith(uri)))

    async def update_options_state(self):
        logger.debug("Updating options during librespot update")

        shuffle = await self.core.tracklist.get_random()
        repeat = await self.core.tracklist.get_repeat()
        repeat_one = repeat and await self.core.tracklist.get_single()

        repeat_state = "track" if repeat_one else "context" if repeat else "off"

        client = self.api.get_client()
        playback = client.current_playback(market="from_token")

        if playback["shuffle_state"] != shuffle:
            logger.debug("Updating mopidy shuffle state to {0} from {1}".format(
                playback["shuffle_state"], shuffle))
            await self.core.tracklist.set_random(playback["shuffle_state"])

        if playback["repeat_state"] != repeat_state:
            logger.debug("Updating mopidy repeat state to {0} from {1}".format(
                playback["repeat_state"], repeat_state))

            if playback["repeat_state"] == "off":
                await self.core.tracklist.set_single(False)
                await self.core.tracklist.set_repeat(False)
            elif playback["repeat_state"] == "track":
                await self.core.tracklist.set_single(True)
                await self.core.tracklist.set_repeat(True)
            elif playback["repeat_state"] == "context":
                await self.core.tracklist.set_single(False)
                await self.core.tracklist.set_repeat(True)

    ##
    # Handle a response from our core
    # This is just our callback from an Async request
    ##

    def handle_result(self, *args, **kwargs):
        id = kwargs.get("id", None)
        method = kwargs.get("method", None)
        response = kwargs.get("response", None)
        error = kwargs.get("error", None)
        request_response = {"id": id, "jsonrpc": "2.0", "method": method}

        if error:
            request_response["error"] = error
            self.set_status(400)

        # We've been handed an AsyncHTTPClient callback. This is the case
        # when our request calls subsequent external requests.
        # We don't need to wrap non-HTTPResponse responses as these are dicts
        elif isinstance(response, tornado.httpclient.HTTPResponse):

            # Digest JSON responses into JSON
            content_type = response.headers.get("Content-Type")
            if content_type.startswith(
                "application/json"
            ) or content_type.startswith("text/json"):
                body = json.loads(response.body)

            # Non-JSON so just copy as-is
            else:
                body = json_encode(response.body)

            request_response["result"] = body

        # Regular ol successful response
        else:
            request_response["result"] = response

        # Write our response

        self.write(request_response)
        self.finish()

# check this is a valid update from librespot
# should probably check the specific event types


def valid_librespot_update(data):
    return (
        isinstance(data, dict)
        and "event" in data
        and "trackID" in data
    )
