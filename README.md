# plex-genres-from-tags
Uses mutagen to read tags from music files and set genres/styles on a Plex server. Created following Plex's adoption of ffmpeg for tag reading and subsequent issues surrounding multiple genre tags.

WARNING: This is a simple script and does not have extensive error management. Use at your own risk. I STRONGLY suggest creating a new music library to test the script and/or use the search string or date options to limit it to a subset of artists. Only run it on your entire music library when you're sure it's behaving as desired. It may take several hours to run on a large music collection.

Customize the following:
- token (auth token - https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- server_name (friendly server name from settings page)
- library_number (found in the URL as source= when browsing a library)
- search_string (optional artist name, limit which artist(s) are changed, matches partial names)
- skip_artists (optional list of artists to ignore, e.g. ['Various Artists'] - albums will still be updated.)
- date_range (optional - change only recently-added albums and related artists - date as yyyy-mm-dd or duration e.g. 6h, 14d, or 1y)
- tag delimiter (how tags are separated in your ID3 tags, usually ";")
- starting_index (in case you have to stop the script. restarts from X index)
- copy to styles (true/false - do you want the genre tags to also replace existing styles)
- verbose mode (true/false - enables extra information while running)
- lock albums (true/false - do you want the album genre/style fields to be locked after updating)
- lock artists (true/false - do you want the artist genre/style fields to be locked after updating)
- path aliases (list of string pairs - in case you're running the script from a different machine with different drive letters. All file paths will have these strings replaced.) e.g.  [['E:','H:'], ['F:','I:']] will replace the server drive letter E with mapped drive letter H and drive F with I
