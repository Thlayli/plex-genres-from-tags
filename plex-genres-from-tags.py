import mutagen
from mutagen import MutagenError
import collections
from tqdm import tqdm
from plexapi.myplex import MyPlexAccount
from plexapi.exceptions import PlexApiException
from plexapi.mixins import EditFieldMixin,EditTagsMixin
import requests
import argparse
import time

# start user variables section

server_name = 'xxxxxxxx'
token = 'xxxxxxxxxxxxxxxxxxxx'
library_number = ##

tag_delimiter = ";"
skip_artists = ['Various Artists']
copy_to_styles = True
verbose_mode = False
lock_albums = True
lock_artists = True
simulate_changes = False
repair_mode = False
path_aliases = []

# end user variables section

parser = argparse.ArgumentParser()
parser.add_argument('-range', nargs='?', default='',  help='date range or start date')
parser.add_argument('-search', nargs='?', default='', help='artist or album search string')
parser.add_argument('-genre', nargs='?', default='', help='genre search string')
parser.add_argument('-index', nargs='?', default=0, help='starting index (for resuming)')
args = parser.parse_args()
search_string = args.search
genre_string = args.genre
date_range = args.range
starting_index = int(args.index)

account = MyPlexAccount(token)
plex = account.resource(server_name).connect()
album_lock_bit = 1 if lock_albums else 0
artist_lock_bit = 1 if lock_artists else 0
library = plex.library.sectionByID(library_number)
plex_filters = {"title": search_string, "addedAt>>": date_range} if date_range != '' else {"title": search_string}
if not genre_string == "":
  plex_filters['genre'] = genre_string
baseurl = str(plex._baseurl).replace('https://','')
selected_artists = collections.OrderedDict()
skipped_artist_albums = collections.OrderedDict()
artist_changes = []
album_changes = []
collect_errors = []
artist_genres = []
album_genres = []
j = 0;
print("\n")

if repair_mode:
  print("Repair mode: if genre and style have the same non-zero count the artist will be skipped")

try:

  # check recently added artists and albums
  for artist in tqdm(library.search(sort="titleSort:asc",filters=plex_filters,libtype='artist'), desc="Looking for Artists"):
    selected_artists.setdefault(artist.key,artist.title)
    
  for album in tqdm(library.search(sort="artist.titleSort:asc",filters=plex_filters,libtype='album'), desc="Looking for Albums"):
    if not album.parentTitle in skip_artists:
      selected_artists.setdefault(album.parentKey,album.parentTitle)
    else:
      # if skip_artists add albums individually to avoid refreshing all albums
      selected_artists.setdefault(album.parentKey,album.parentTitle)
      skipped_artist_albums.setdefault(album.parentTitle, {})
      skipped_artist_albums[album.parentTitle].setdefault(album.key,album.title)

  if starting_index > len(selected_artists):
    starting_index = 0
    tqdm.write("Starting index out of range. Starting from 0.")


  for (artist_key,artist_title) in tqdm(list(selected_artists.items())[starting_index:], desc="Scanning Tags", total=len(selected_artists),initial=starting_index):

    j = 0
    artist = library.fetchItem(artist_key)
    artist.reload()
    time.sleep(1)
    artist_genres.clear()
    
    try:

      tqdm.write("┌ Scanning: "+str(artist_title))
      
      if not repair_mode or len(artist.genres) != len(artist.styles) or len(artist.genres) == 0:
        
        # remove existing artist genres
        if hasattr(artist,'genres') and artist.genres:
          if verbose_mode:
            tqdm.write("│ Removing: "+str([genre.tag for genre in artist.genres])+" from genres")
          if not simulate_changes:
            artist.removeGenre([genre.tag for genre in artist.genres], False)

        # remove existing artist styles
        if copy_to_styles and artist.styles:
          if hasattr(artist,'styles') and artist.styles:
            if verbose_mode:
              tqdm.write("│ Removing: "+str([style.tag for style in artist.styles])+" from styles")
            if not simulate_changes:
              artist.removeStyle([style.tag for style in artist.styles], False)
          if verbose_mode:
            tqdm.write("│  Removed: "+str(len(artist.genres))+" genres & "+str(len(artist.styles))+" styles")
        else:
          if artist.genres and verbose_mode:
            tqdm.write("│  Removed: "+str(len(artist.genres))+" genres")

        # set selected_albums to skipped_artist_albums if skip artist
        if not artist.title in skip_artists:
          selected_albums = artist.albums()
        else:
          selected_albums = []
          if verbose_mode:
            tqdm.write('│  Filter includes: '+str([v for (k,v) in skipped_artist_albums[artist_title].items()]))
          for k in skipped_artist_albums[artist_title]:
            selected_albums.append(library.fetchItem(k))
        
        # for each album
        for album in selected_albums:

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
                    if not gs in album_genres:
                      album_genres.append(gs.strip())
                      artist_genres.append(gs.strip())
                else:
                  if not genre in album_genres:
                    album_genres.append(genre.strip())
                  if not genre in artist_genres:
                    artist_genres.append(genre.strip())
              
              # list tags for album
              album_glist = list(dict.fromkeys(album_genres))
              album_changes.append([artist.title+' - '+album.title,album.key,album_glist])
              tqdm.write("│ │     Tags: "+str(album_glist))

              # clear existing genres
              if hasattr(album,'genres') and album.genres:
                if verbose_mode:
                  tqdm.write("│ │ Removing: "+str([genre.tag for genre in album.genres])+" from genres")
                gcount = len(album.genres)
                if not simulate_changes:
                  album.removeGenre([genre.tag for genre in album.genres], False)

              # clear existing styles
              if copy_to_styles and album.styles:
                scount = 0
                if hasattr(album,'styles') and album.styles:
                  if verbose_mode:
                    tqdm.write("│ │ Removing: "+str([style.tag for style in album.styles])+" from styles")
                  scount = len(album.styles)
                  if not simulate_changes:
                    album.removeStyle([style.tag for style in album.styles], False)
                if verbose_mode:
                  tqdm.write("│ │  Removed: "+str(gcount)+" genres & "+str(scount)+" styles")
              else:
                if album.genres and verbose_mode:
                  tqdm.write("│ │  Removed: "+str(gcount)+" genres")

              # make album changes
              try:
                album_direct = library.fetchItem(album.key)
                if verbose_mode:
                  tqdm.write('│ │  Adding: '+str(album_glist))
                if copy_to_styles:
                  if not simulate_changes:
                    album_direct.editTags("genre", album_glist, album_lock_bit).editTags("style", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres/styles")
                else:
                  if not simulate_changes:
                    album_direct.editTags("genre", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres")
              except PlexApiException as err:
                tqdm.write('│ └    Server Error: '+str(err))
                  
              gcount = 0
              scount = 0
              

            else:
             tqdm.write("│ └    Error: can't read tags")
             
            # may prevent errors
            time.sleep(1)

          except MutagenError as e:
            tqdm.write("│ └    Error: "+str(str(e).split(";")[0]))
        
        # list tags for artist
        artist_glist = list(dict.fromkeys(artist_genres))
        artist_changes.append([artist.title,artist.key,artist_glist])


        # make artist changes
        if not artist_title in skip_artists:
          try:
            artist_direct = library.fetchItem(artist.key)
            if verbose_mode:
              tqdm.write('│   Adding: '+str(artist_glist))
            if copy_to_styles:
              if not simulate_changes:
                artist_direct.editTags("genre", artist_glist, artist_lock_bit).editTags("style", artist_glist, artist_lock_bit)
              tqdm.write("│    Added: "+str(len(artist_glist))+" genres/styles")
            else:
              if not simulate_changes:
                artist_direct.editTags("genre", artist_glist, artist_lock_bit)
              tqdm.write("│   Added: "+str(len(artist_glist))+" genres")
          except PlexApiException as err:
            collect_errors.append("Server Error: "+str(err))
            tqdm.write('│    Error: '+str(err))
            
        else:
          tqdm.write("│ Skipping: "+str(artist.title))
          
      else:
        tqdm.write("│ Skipping: "+str(artist.title))
        # may prevent errors
        time.sleep(1)

    except requests.exceptions.RequestException as err:
      collect_errors.append("Connection Error: "+str(err))
      tqdm.write('│  Error: '+str(err))

    tqdm.write("└ "+(str(j)+" albums checked for "+artist.title)+"\n")
    

except requests.exceptions.RequestException as err:
  collect_errors.append("Connection Error: "+str(err))
  tqdm.write('│  Error: '+str(err))

print("\n"+str(len(artist_changes)),"artists had genres updated from "+str(len(album_changes))+' albums')
if len(collect_errors) > 0:
  print("Errors:\n",str(collect_errors))
