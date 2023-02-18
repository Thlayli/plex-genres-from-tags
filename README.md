# plex-genres-from-tags
Uses mutagen to read tags from music files and set genres/styles on a Plex server. Created following Plex's adoption of ffmpeg for tag reading and subsequent issues surrounding multiple genre tags.

WARNING: This is a simple script and does not have extensive error management. Use at your own risk. I STRONGLY suggest creating a new music library to test the script and/or use the search string or date options to limit it to a subset of artists. Only run it on your entire music library when you're sure it's behaving as desired. It may take several hours to run on a large music collection.

Set the following at runtime: e.g. "plex-genres-from-tags.py -range=12h"
- -range=datetime (change only recent albums and related artists - date as yyyy-mm-dd or duration e.g. 6h, 14d, or 1y)
- -search=string (optional artist name, limit which artist(s) are changed, matches partial names)
- -index=integer (in case you have to stop the script. restarts from X index)
- -genre=string (limit changes to albums/artists matching a specific genre)
- -simulate=true (default false) - don't write changes to plex
- -repair=true  (default false) - only change artists with mismatched style/genre count or no genres/styles)

Customize the following in the script file:
- token (auth token - https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- server_name (friendly server name from settings page)
- library_number (found in the URL as source= when browsing a library)
- skip_artists (optional list of artists to ignore, e.g. ['Various Artists'] - albums will still be updated.)
- tag delimiter (how tags are separated in your ID3 tags, usually ";")
- style_source ("genre", "grouping", or "none" - choose where style tags come from, copied from genres, the grouping tags, or skip styles tags)
- style_fallback ("remove", "ignore", or "genre" - choose what happens to plex tags if styles aren't found in style_source)
- genre_fallback ("remove" or "ignore" - choose what happens to plex tags when genre file tags aren't found)
- verbose mode (true/false - enables extra information while running)
- lock albums (true/false - do you want the album genre/style fields to be locked after updating)
- lock artists (true/false - do you want the artist genre/style fields to be locked after updating)
- path aliases (list of string pairs - in case you're running the script from a different machine with different drive letters. All file paths will have these strings replaced.) e.g.  [['E:','H:'], ['F:','I:']] will replace the server drive letter E with mapped drive letter H and drive F with I)
- path_prepend (string to insert before each file path to help with remapping mounted drives in Mac/linux)
