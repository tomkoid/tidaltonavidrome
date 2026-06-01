#!/usr/bin/env python3

import hashlib
import requests
import tidalapi
from urllib.parse import quote
from rapidfuzz import fuzz
import re

# ==========================================
# CONFIGURATION
# ==========================================

TIDAL_USERNAME = ""
TIDAL_PASSWORD = ""

NAVIDROME_URL = "https://"
NAVIDROME_USERNAME = ""
NAVIDROME_PASSWORD = ""

CLIENT_NAME = "tidal2navidrome"

# ==========================================
# NAVIDROME / SUBSONIC API
# ==========================================

class Navidrome:
    def __init__(self, url: str, username: str, password: str):
        self.url: str = url.rstrip("/")
        self.username: str = username
        self.password: str = password

    def _params(self):
        salt = "tidal2navidrome"
        token = hashlib.md5(
            (self.password + salt).encode()
        ).hexdigest()

        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": "1.16.1",
            "c": CLIENT_NAME,
            "f": "json",
        }

    def request(self, endpoint, **extra):
        params = self._params()
        params.update(extra)

        r = requests.get(
            f"{self.url}/rest/{endpoint}",
            params=params,
            timeout=30,
        )

        r.raise_for_status()

        data = r.json()
        return data["subsonic-response"]


    def normalize(self, text: str) -> str:
        text = text.lower()

        # remove stuff in parentheses/brackets
        text = re.sub(r"\(.*?\)", "", text)
        text = re.sub(r"\[.*?\]", "", text)

        # remove common release suffixes
        text = re.sub(
            r"\b(remaster(ed)?|radio edit|explicit|clean|mono|stereo)\b",
            "",
            text,
        )

        # keep only letters/numbers/spaces
        text = re.sub(r"[^a-z0-9 ]", " ", text)

        # collapse whitespace
        text = " ".join(text.split())

        return text


    def search_track(self, title, artist):
        result = self.request(
            "search3.view",
            query=f"{artist} {title}",
            songCount=50,
        )

        songs = result.get("searchResult3", {}).get("song", [])

        target_title = self.normalize(title)
        target_artist = self.normalize(artist)

        best_song = None
        best_score = 0

        for song in songs:
            song_title = self.normalize(song.get("title", ""))
            song_artist = self.normalize(song.get("artist", ""))

            title_score = fuzz.token_set_ratio(
                target_title,
                song_title,
            )

            artist_score = fuzz.token_set_ratio(
                target_artist,
                song_artist,
            )

            score = (
                title_score * 0.75 +
                artist_score * 0.25
            )

            if score > best_score:
                best_score = score
                best_song = song

        if best_song and best_score >= 80:
            print(
                f"    ✓ Match {best_score:.1f}% "
                f"-> {best_song['artist']} - {best_song['title']}"
            )
            return best_song["id"]

        return None

    def create_playlist(self, name, song_ids):
        if not song_ids:
            print(f"Skipping empty playlist: {name}")
            return

        params = self._params()

        for sid in song_ids:
            params.setdefault("songId", []).append(sid)

        params["name"] = name

        r = requests.get(
            f"{self.url}/rest/createPlaylist.view",
            params=params,
            timeout=60,
        )

        r.raise_for_status()

# ==========================================
# TIDAL
# ==========================================

def login_tidal():
    session = tidalapi.Session()

    (data, future) = session.login_oauth()
    print(f"visit this link and authenticate: https://{data.verification_uri_complete}")

    future.result()

    return session

# ==========================================
# MAIN
# ==========================================

def main():
    tidal = login_tidal()

    user = tidal.user

    playlists = user.playlists()

    nav = Navidrome(
        NAVIDROME_URL,
        NAVIDROME_USERNAME,
        NAVIDROME_PASSWORD,
    )

    print(f"Found {len(playlists)} playlists")

    for playlist in playlists:
        print(f"\nProcessing: {playlist.name}")

        matched_ids = []

        tracks = playlist.tracks()

        for track in tracks:
            title = track.name

            if track.artists:
                artist = track.artists[0].name
            else:
                artist = ""

            print(f"  Searching: {artist} - {title}")

            song_id = nav.search_track(title, artist)

            if song_id:
                matched_ids.append(song_id)
                print("    ✓ Found")
            else:
                print("    ✗ Missing")

        print(
            f"Creating playlist '{playlist.name}' "
            f"({len(matched_ids)} tracks)"
        )

        nav.create_playlist(
            playlist.name,
            matched_ids,
        )

    print("\nDone!")

if __name__ == "__main__":
    main()
