import pathlib

import pkg_resources
from mopidy import config, ext

__version__ = pkg_resources.get_distribution("Mopidy-Spotify").version


class Extension(ext.Extension):

    dist_name = "Mopidy-Spotify"
    ext_name = "spotify"
    version = __version__

    def get_default_config(self):
        return config.read(pathlib.Path(__file__).parent / "ext.conf")

    def get_config_schema(self):
        schema = super().get_config_schema()

        schema["client_id"] = config.String()
        schema["client_secret"] = config.Secret()
        schema["refresh_token"] = config.Secret()
        schema["device_name"] = config.String()

        schema["bitrate"] = config.Integer(choices=(96, 160, 320))
        schema["volume_normalization"] = config.Boolean()
        schema["private_session"] = config.Boolean()

        schema["timeout"] = config.Integer(minimum=0)

        schema["cache_dir"] = config.Deprecated()  # since 2.0
        schema["settings_dir"] = config.Deprecated()  # since 2.0

        schema["allow_cache"] = config.Boolean()
        schema["allow_network"] = config.Boolean()
        schema["allow_playlists"] = config.Boolean()

        schema["search_album_count"] = config.Integer(minimum=0, maximum=200)
        schema["search_artist_count"] = config.Integer(minimum=0, maximum=200)
        schema["search_track_count"] = config.Integer(minimum=0, maximum=200)

        schema["toplist_countries"] = config.List(optional=True)

        return schema

    def setup(self, registry):
        from mopidy_spotify.backend import SpotifyBackend

        registry.add(
            "http:app", {"name": "librespot", "factory": librespot_http_factory})
        registry.add("backend", SpotifyBackend)


def librespot_http_factory(config, core):
    from .handlers import LibrespotHttpHandler
    return [
        (r".*", LibrespotHttpHandler, {"core": core, "config": config}),
    ]
