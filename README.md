# plex-genres-from-tags
Uses mutagen to read tags from music files and set genres/styles on a Plex server. Created following Plex's adoption of ffmpeg for tag reading and subsequent issues surrounding multiple genre tags.

WARNING
This is a simple script and does not have extensive error management. Use at your own risk. I STRONGLY suggest creating a new music library to test the script on. Only run it on your main music library when you're sure it's behaving as desired. Interrupting the script before it is complete (or experiencing a fatal error) will leave empty genre tags since the API behavior necessitated removing the tags first, then replacing them as a second step.

Customize the following:
- account: auth token (https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- server name (friendly server name from settings page)
- library number (found in the URL as source= when browsing a library)
- search string (optional artist name, limit which artist(s) are changed, matches partial names)
- skip_artists = ['Various Artists']
- date_range [start date as yyyy-mm-dd OR #d, #w, #m, #y, e.g. 14d, 1y, etc.]
- tag delimiter (how tags are separated in your ID3 tags, usually ;)
- starting_index (in case you have to stop the script. restarts from X index)
- copy to styles (true/false - do you want the genre tags to also replace existing styles)
- verbose mode (true/false - enables extra information while running)
- lock albums (true/false - do you want the album genre/style fields to be locked after updating)
- lock artists (true/false - do you want the artist genre/style fields to be locked after updating)
- path aliases (list of string pairs - in case you're running the script from a different machine with different drive letters. All file paths will have these strings replaced.) e.g.  [['E:','H:']] will replace the server drive letter E with mapped drive letter H.
