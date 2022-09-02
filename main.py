import mutagen
from mutagen import MutagenError
from tqdm import tqdm
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import PlexApiException
from plexapi.mixins import EditFieldMixin,EditTagsMixin

# start user variables section

server_name = 'xxxxxxxx'
token = 'xxxxxxxxxxxxxxxxxxxx'
library_number = ##

search_string = ''
date_range = ''
tag_delimiter = ";"
starting_index = 0
skip_artists = ['Various Artists']
copy_to_styles = True
verbose_mode = False
lock_albums = True
lock_artists = False
path_aliases = []

# end user variables section

account = MyPlexAccount(token)
plex = account.resource(server_name).connect()
album_lock_bit = 1 if lock_albums else 0
artist_lock_bit = 1 if lock_artists else 0
library = plex.library.sectionByID(library_number)
plex_filters = {"title": search_string, "addedAt>>": date_range} if date_range != '' else {"title": search_string}
baseurl = str(plex._baseurl).replace('https://','')
artist_changes = []
album_changes = []
collect_errors = []
selected_artists = set()
artist_genres = set()
album_genres = set()
j = 0;
print("\n")

try:

  # check recently added albums and collect artists
  for album in tqdm(library.search(filters=plex_filters,libtype='album'), desc="Looking for Albums"):
    selected_artists.add(album.parentKey)

  for artist in tqdm(library.search(filters=plex_filters,libtype='artist'), desc="Looking for Artists"):
    selected_artists.add(artist.key)

  for artist_key in tqdm(list(selected_artists)[starting_index:], desc="Scanning Tags"):

    artist = library.fetchItem(artist_key)

    if artist.title not in skip_artists:

      j = 0
      artist.reload()
      artist_genres.clear()
      
      try:

        tqdm.write("┌ Scanning: "+str(artist.title))
        
        # remove existing artist genres
        if hasattr(artist,'genres') and artist.genres:
          if verbose_mode:
            tqdm.write("│ Removing: "+str([genre.tag for genre in artist.genres])+" from genres")
          artist.removeGenre([genre.tag for genre in artist.genres], False)

        # remove existing artist styles
        if copy_to_styles and artist.genres:
          if hasattr(artist,'styles') and artist.styles:
            if verbose_mode:
              tqdm.write("│ Removing: "+str([style.tag for style in artist.styles])+" from styles")
            artist.removeStyle([style.tag for style in artist.styles], False)
          tqdm.write("│  Removed: "+str(len(artist.genres))+" genres & "+str(len(artist.styles))+" styles")
        else:
          if artist.genres:
            tqdm.write("│  Removed: "+str(len(artist.genres))+" genres")
        
        # for each album
        for album in artist.albums():

          album_genres.clear()
          tqdm.write("│ ┌ Scanning: "+str(album.title))
          
          # get filename and adjust drive/path aliases
          file = str(album.tracks()[0].media[0].parts[0].file).replace(baseurl,'')
          for alias in path_aliases:
            file = file.replace(alias[0], alias[1])
            
          if verbose_mode:
            tqdm.write("│ │   Source: "+file)
          j = j+1
          
          # extract genre tags
          try:
            tags = mutagen.File(file, easy=True)
            if tags == None:
              tags = []
             
            if 'genre' in tags:
              genre_list = tags['genre']
              # add album genres to artist genres list
              for genre in genre_list:
                if tag_delimiter in genre:
                  genre_split = genre.split(tag_delimiter)
                  for gs in genre_split:
                     album_genres.add(gs.strip())
                     artist_genres.add(gs.strip())
                else:
                  album_genres.add(genre)
                  artist_genres.add(genre)
              tqdm.write("│ │     Tags: "+str(list(album_genres)))
              
              # list tags for album
              album_glist = list(dict.fromkeys(album_genres))
              album_changes.append([artist.title+' - '+album.title,album.key,album_glist])

              # clear existing genres
              if hasattr(album,'genres') and album.genres:
                if verbose_mode:
                  tqdm.write("│ │ Removing: "+str([genre.tag for genre in album.genres])+" from genres")
                gcount = len(album.genres)
                album.removeGenre([genre.tag for genre in album.genres], False)

              # clear existing styles
              if copy_to_styles and album.genres:
                scount = 0
                if hasattr(album,'styles') and artist.styles:
                  if verbose_mode:
                    tqdm.write("│ │ Removing: "+str([style.tag for style in album.styles])+" from styles")
                  scount = len(album.styles)
                  album.removeStyle([style.tag for style in album.styles], False)
                tqdm.write("│ │  Removed: "+str(gcount)+" genres & "+str(scount)+" styles")
              else:
                if album.genres:
                  tqdm.write("│ │  Removed: "+str(gcount)+" genres")

              # make album changes
              try:
                album_direct = library.fetchItem(album.key)
                if verbose_mode:
                  tqdm.write('│ │  Adding: '+str(album_glist))
                if copy_to_styles:
                  album_direct.editTags("genre", album_glist, album_lock_bit).editTags("style", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres/styles")
                else:
                  album_direct.editTags("genre", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres")
              except PlexApiException as err:
                tqdm.write('│ └    Error: '+str(err))
                  
              gcount = 0
              scount = 0
              

            else:
             tqdm.write("│ └    Error: can't read tags")

          except MutagenError as e:
            tqdm.write("│ └    Error: "+str(str(e).split(";")[0]))
        
        # list tags for artist
        artist_glist = list(dict.fromkeys(artist_genres))
        artist_changes.append([artist.title,artist.key,artist_glist])


        # make artist changes
        try:
          artist_direct = library.fetchItem(artist.key)
          if verbose_mode:
            tqdm.write('│  Adding: '+str(artist_glist))
          if copy_to_styles:
            artist_direct.editTags("genre", artist_glist, artist_lock_bit).editTags("style", artist_glist, artist_lock_bit)
            tqdm.write("│    Added: "+str(len(artist_glist))+" genres/styles")
          else:
            artist_direct.editTags("genre", artist_glist, artist_lock_bit)
            tqdm.write("│   Added: "+str(len(artist_glist))+" genres")
        except PlexApiException as err:
          collect_errors.append("Album Error: "+err)
          tqdm.write('│    Error: '+str(err))


      except PlexApiException as err:
        collect_errors.append("Artist Error: "+err)
        tqdm.write('│  Error: '+str(err))

      tqdm.write("└ "+(str(j)+" albums checked for "+artist.title)+"\n")
      
    else:
      
      tqdm.write("－ Skipping: "+str(artist.title))

except PlexApiException as err:
  collect_errors.append("Server Error: "+err)
  tqdm.write('│  Error: '+str(err))


print(str(len(artist_changes)),"artists had genres updated from "+str(len(album_changes))+' albums')
if len(collect_errors) > 0:
  print("Errors:\n",str(collect_errors))
