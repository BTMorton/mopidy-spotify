import json
import time
import tornado.ioloop
import logging

from pykka.messages import ProxyCall

from mopidy.core import PlaybackState, CoreListener
from mopidy.audio import AudioListener

from pprint import pprint

logger = logging.getLogger(__name__)


class LibrespotHttpHandler(tornado.web.RequestHandler):
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
        self.ioloop = tornado.ioloop.IOLoop.current()
        self._state = PlaybackState.STOPPED

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

            # if it's a start event, stop whatever is playing
            if event == "start":
                await self.core.playback.stop()
            # if it's a stop event, check if we're active and stop
            elif event == "stop":
                current_track_uri = await self.get_current_track_uri()
                current_state = await self.core.playback.get_state()

                if current_state != PlaybackState.STOPPED and current_track_uri.startswith("spotify:"):
                    await self.core.playback.stop()
                    AudioListener.send("reached_end_of_stream")
            # on a change event, just trigger a track change
            elif event == "change":
                await self.change_track(track_uri)
            # if we're playing, there are options
            elif event == "playing":
                current_track_uri = await self.get_current_track_uri()
                current_state = await self.core.playback.get_state()

                # if we're already playing this track, this is most likely actually a seek event
                if current_state == PlaybackState.PLAYING and current_track_uri == track_uri:
                    CoreListener.send(
                        "seeked",
                        time_position=params["positionMS"]
                    )
                # if we're not already playing, just trigger a track change
                else:
                    await self.change_track(track_uri)
            # a pause also has options
            elif event == "paused":
                current_state = await self.core.playback.get_state()
                current_track = await self.core.playback.get_current_tl_track()
                next_track = await self.core.tracklist.eot_track(current_track)

                # if there is another source active, do nothing
                if current_track is not None and not current_track.track.uri.startswith("spotify:"):
                    None
                # if we're part-way through a track, this is a user pause
                elif params["positionMS"] > 0:
                    self.pause(params["positionMS"])
                # if the current state is paused, this is librespot responding to the pause action
                elif current_state == PlaybackState.PAUSED:
                    self.trigger_pause(params["positionMS"])
                # if there is no next track scheduled, we're at the end of the playlist, so pause
                elif next_track is None:
                    self.pause(params["positionMS"])
                # otherwise, we've hit the end of the track, so we need mopidy to schedule the next one
                else:
                    res = self.core.actor_ref.ask(
                        ProxyCall(
                            attr_path=["playback", "_on_about_to_finish"],
                            args=[],
                            kwargs={},
                        )
                    )
            # on a volume event, treat volume 0 as mute and otherwise set the volume
            elif event == "volume_set":
                muted = await self.core.mixer.get_mute()
                volume = data["volume"]

                if muted and volume > 0:
                    await self.core.mixer.set_mute(False)
                elif not muted and volume == 0:
                    await self.core.mixer.set_mute(True)

                if volume > 0:
                    await self.core.mixer.set_volume(data["volume"])

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
        current_track = await self.core.playback.get_current_tl_track()

        current_track_uri = ""
        if current_track is not None and current_track.track is not None:
            current_track_uri = current_track.track.uri

        return current_track_uri

    # update mopidy that a track change has occured
    async def change_track(self, uri):
        current_track_uri = await self.get_current_track_uri()

        # if something else was playing, stop it
        if not current_track_uri.startswith("spotify:"):
            await self.core.playback.stop()

        # get the track list entry and play it
        tl_track = await self.ensure_track_in_tracklist(uri)
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
    async def ensure_track_in_tracklist(self, uri):
        tl_tracks = await self.core.tracklist.filter({"uri": [uri]})

        if len(tl_tracks) == 0:
            tl_tracks = await self.core.tracklist.add(uris=[uri])

        return tl_tracks[0]

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
