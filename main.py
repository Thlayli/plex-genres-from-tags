import mutagen
from mutagen import MutagenError
from tqdm import tqdm
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import PlexApiException
from plexapi.mixins import EditFieldMixin,EditTagsMixin

# start user variables section

account = MyPlexAccount('xxxxxxxxxxxx')
plex = account.resource('xxxxxxxx').connect()
library_number = ##
search_string = ''
tag_delimiter = ";"
copy_to_styles = True
verbose_mode = True
lock_fields = True
path_aliases = []

# end user variables section

j = 0;
lock_value = 1 if lock_fields else 0
library = plex.library.sectionByID(library_number)
baseurl = str(plex._baseurl).replace('https://','')
artist_changes = []
album_changes = []
artist_genres = set()
album_genres = set()

print("\n")

for artist in tqdm(library.search(search_string,libtype='artist'), desc="Scanning Tags"):

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
          
          # flip tags for album
          album_rev = list(album_genres)
          album_rev.reverse()
          album_changes.append([artist.title+' - '+album.title,album.key,album_rev])

          # clear existing genres
          if hasattr(album,'genres') and album.genres:
            if verbose_mode:
              tqdm.write("│ │ Removing: "+str([genre.tag for genre in album.genres])+" from genres")
            gcount = len(album.genres)
            album.removeGenre([genre.tag for genre in album.genres], False)

          # clear existing styles
          if copy_to_styles and album.genres:
            if hasattr(album,'styles') and artist.styles:
              if verbose_mode:
                tqdm.write("│ │ Removing: "+str([style.tag for style in album.styles])+" from styles")
              scount = len(album.styles)
              album.removeStyle([style.tag for style in album.styles], False)
            tqdm.write("│ └  Removed: "+str(gcount)+" genres & "+str(scount)+" styles")
          else:
            if album.genres:
              tqdm.write("│ └  Removed: "+str(gcount)+" genres")
            else:
              tqdm.write("│ └")

          # make album changes
          try:
            album_direct = library.fetchItem(album.key)
            if verbose_mode:
              tqdm.write('│ │  Adding: '+str(album_rev))
            if copy_to_styles:
              album_direct.editTags("genre", album_rev, lock_value)
              album_direct.editTags("style", album_rev, lock_value)
              tqdm.write("│ │    Added: "+str(len(album_rev))+" genres/styles")
            else:
              album_direct.editTags("genre", album_rev, lock_value)
              tqdm.write("│ │    Added: "+str(len(album_rev))+" genres")
          except PlexApiException as err:
            tqdm.write('│ │    Error: '+str(err))
              
          gcount = 0
          scount = 0
          

        else:
         tqdm.write("│ └    Error: can't read tags")

      except MutagenError as e:
        tqdm.write("│ └    Error: "+str(str(e).split(";")[0]))
    
    # save tags for artist
    artist_rev = list(artist_genres)
    artist_rev.reverse()
    artist_changes.append([artist.title,artist.key,artist_rev])


    # make artist changes
    try:
      artist_direct = library.fetchItem(artist.key)
      if verbose_mode:
        tqdm.write('│  Adding: '+str(artist_rev))
      if copy_to_styles:
        artist_direct.editTags("genre", artist_rev, lock_value)
        artist_direct.editTags("style", artist_rev, lock_value)
        tqdm.write("│    Added: "+str(len(artist_rev))+" genres/styles")
      else:
        artist_direct.editTags("genre", artist_rev, lock_value)
        tqdm.write("│   Added: "+str(len(artist_rev))+" genres")
    except PlexApiException as err:
      tqdm.write('│    Error: '+str(err))


  except PlexApiException as err:
    tqdm.write('│  Error: '+str(err))

  tqdm.write("└ "+(str(j)+" albums checked for "+artist.title)+"\n")
  
print("\n")

print(str(len(artist_changes)),"artists had genres updated from "+str(len(album_changes))+' albums')
