#!/usr/bin/python

import os
import requests

event = {
    "event": os.environ.get("PLAYER_EVENT", "none"),
    "trackID": os.environ.get("TRACK_ID", ""),
}

print("Handling " + event["event"] + " event update")

if event["event"] == "change":
    event["oldTrackID"] = process.env.OLD_TRACK_ID
elif event["event"] == "playing" or event["event"] == "paused":
    event["durationMS"] = int(os.environ.get("DURATION_MS"))
    event["positionMS"] = int(os.environ.get("POSITION_MS"))
elif event["event"] == "volume_set":
    event["volume"] = int(os.environ.get("VOLUME"))
print(event)

try:
    response = requests.post("http://localhost:6680/librespot/", json=event)

    if response.ok:
        print("Successfully handled event")
    else:
        print("An error occured while handling event: " +
              response.content.decode('utf-8'))
except Exception as e:
    print("An error occured while handling event: {0}".format(e))
