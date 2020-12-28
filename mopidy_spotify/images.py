import itertools
import logging
import operator
import urllib.parse

from mopidy import models
from pprint import pprint
from mopidy_spotify.utils import flatten, iterate, locale

# NOTE: This module is independent of libspotify and built using the Spotify
# Web APIs. As such it does not tie in with any of the regular code used
# elsewhere in the mopidy-spotify extensions. It is also intended to be used
# across both the 1.x and 2.x versions.

_API_MAX_IDS_PER_REQUEST = 50

_cache = {}  # (type, id) -> [Image(), ...]

logger = logging.getLogger(__name__)

DEFAULT_IMAGES = {
    "spotify:playlists": [models.Image(uri="/iris/assets/backgrounds/discover.jpg", height=1013, width=1920)],
    "spotify:top": [models.Image(uri="/iris/assets/backgrounds/browse-default.jpg", height=275, width=275)],
    "spotify:your": [models.Image(uri="/iris/assets/backgrounds/browse-spotify.jpg", height=275, width=275)],
    "spotify:playlists:featured": [models.Image(uri="/iris/assets/backgrounds/discover.jpg", height=1013, width=1920)],
    "spotify:genre": [models.Image(uri="/iris/assets/backgrounds/browse-default.jpg", height=275, width=275)],
    "spotify:new": [models.Image(uri="/iris/assets/backgrounds/browse-default.jpg", height=275, width=275)],
    "spotify:top:tracks": [models.Image(uri="/iris/assets/backgrounds/browse-spotify.jpg", height=275, width=275)],
    "spotify:top:artists": [models.Image(uri="/iris/assets/backgrounds/browse-artists.jpg", height=275, width=275)],
    "spotify:your:albums": [models.Image(uri="/iris/assets/backgrounds/browse-albums.jpg", height=275, width=275)],
    "spotify:your:artists": [models.Image(uri="/iris/assets/backgrounds/browse-artists.jpg", height=275, width=275)],
    "spotify:your:tracks": [models.Image(uri="/iris/assets/backgrounds/browse-spotify.jpg", height=275, width=275)],
}


def get_images(api, uris, config):
    result = {}
    uri_type_getter = operator.itemgetter("type")

    for uri in uris:
        if uri in DEFAULT_IMAGES:
            result[uri] = DEFAULT_IMAGES[uri]

    parsed_uris = (_parse_uri(u) for u in uris if u not in DEFAULT_IMAGES)
    uris = sorted((
        uri
        for uri in parsed_uris
        if uri
    ), key=uri_type_getter)

    for uri_type, group in itertools.groupby(uris, uri_type_getter):
        batch = []
        for uri in group:
            if uri["key"] in _cache:
                result[uri["uri"]] = _cache[uri["key"]]
            elif uri_type == "playlist":
                result.update(_process_uri(api, uri))
            else:
                batch.append(uri)
                if len(batch) >= _API_MAX_IDS_PER_REQUEST:
                    result.update(_process_uris(api, uri_type, batch, config))
                    batch = []
        result.update(_process_uris(api, uri_type, batch, config))
    return result


def _parse_uri(uri):
    parsed_uri = urllib.parse.urlparse(uri)
    uri_type, uri_id = None, None

    if parsed_uri.scheme == "spotify":
        split = parsed_uri.path.split(":")
        if len(split) >= 2:
            (uri_type, uri_id) = split

    elif parsed_uri.scheme in ("http", "https"):
        if parsed_uri.netloc in ("open.spotify.com", "play.spotify.com"):
            uri_type, uri_id = parsed_uri.path.split("/")[1:3]

    supported_types = ("track", "album", "artist", "playlist", "genre")
    if uri_type and uri_type in supported_types and uri_id:
        return {
            "uri": uri,
            "type": uri_type,
            "id": uri_id,
            "key": (uri_type, uri_id),
        }

    logger.debug(f"Could not parse {repr(uri)} as a Spotify URI")
    return None


def _process_uri(api, uri):
    data = api._get(f"{uri['type']}s/{uri['id']}")
    _cache[uri["key"]] = tuple(_translate_image(i) for i in data["images"])
    return {uri["uri"]: _cache[uri["key"]]}


def _process_genres(api, uris, config):
    result = {}
    lookup = [uri for uri in uris if uri["key"] not in _cache]

    if len(lookup) > 0:
        all_genres = flatten(
            data.get("items")
            for data in iterate(api, api.categories(limit=50, locale=locale(config), country=config["country"]), "categories")
        )

        for genre in all_genres:
            _cache[("genre", genre["id"])] = tuple(
                _translate_image(i) for i in genre["icons"]
            )

    for uri in uris:
        if uri["key"] in _cache:
            result[uri["uri"]] = _cache[uri["key"]]

    return result


def _process_uris(api, uri_type, uris, config):
    if uri_type == "genre":
        return _process_genres(api, uris, config)

    result = {}
    ids = [u["id"] for u in uris]
    ids_to_uris = {u["id"]: u for u in uris}

    if not uris:
        return result

    data = flatten(
        api._get(uri_type + "s?ids=" + ",".join(idset)).get(uri_type + "s")
        for idset in [ids[i:i + 20] for i in range(0, len(ids), 20)]
    )
    for item in data:
        if not item:
            continue

        if "linked_from" in item:
            uri = ids_to_uris[item["linked_from"]["id"]]
        else:
            uri = ids_to_uris[item["id"]]

        if uri["key"] not in _cache:
            if uri_type == "track":
                album_key = _parse_uri(item["album"]["uri"])["key"]
                if album_key not in _cache:
                    _cache[album_key] = tuple(
                        _translate_image(i) for i in item["album"]["images"]
                    )
                _cache[uri["key"]] = _cache[album_key]
            else:
                _cache[uri["key"]] = tuple(
                    _translate_image(i) for i in item["images"]
                )
        result[uri["uri"]] = _cache[uri["key"]]

    return result


def _translate_image(i):
    return models.Image(uri=i["url"], height=i["height"], width=i["width"])
