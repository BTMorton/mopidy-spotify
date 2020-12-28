import logging
import time

# no monotonic python 2
if not hasattr(time, 'monotonic'):
    time.monotonic = time.time

import requests
import spotipy

logger = logging.getLogger(__name__)


def get_fresh_token(config):
    try:
        logger.debug("authenticating")
        response = get_fresh_token_from_spotify(config)
        logger.debug("authentication response: %s", response.content)
        token_response = response.json()
        return token_response
    except requests.exceptions.RequestException as e:
        logger.error('Refreshing the auth token failed: %s', e)
    except ValueError as e:
        logger.error('Decoding the JSON auth token response failed: %s', e)


def get_fresh_token_from_spotify(config):
    spotify_token_url = "https://accounts.spotify.com/api/token"
    logger.debug("authentication using spotify on: %s", spotify_token_url)
    auth = (config['client_id'], config['client_secret'])
    return requests.post(spotify_token_url, auth=auth, data={
        'grant_type': 'refresh_token',
        'refresh_token': config['refresh_token'],
    })


def token_is_fresh(sp, access_token_expires):
    return sp is not None and time.monotonic() < access_token_expires - 60


class SpotifyAPI:
    def __init__(self, config):
        self._config = config
        self._sp = None
        self._access_token = None
        self._access_token_expires = None
        self.user_id = None

    def get_client(self):
        if token_is_fresh(self._sp, self._access_token_expires):
            return self._sp

        token_res = get_fresh_token(self._config["spotify"])
        if token_res is None or 'access_token' not in token_res:
            logger.warn('Did not receive authentication token!')
            return None

        self._access_token = token_res['access_token']
        self._access_token_expires = time.monotonic() + token_res['expires_in']
        self._sp = spotipy.Spotify(auth=self._access_token)

        self.user_id = self._sp.user_id = self._sp.current_user()["id"]
        return self._sp
