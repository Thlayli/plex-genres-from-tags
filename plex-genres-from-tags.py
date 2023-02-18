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
import pandas as pd
from types import SimpleNamespace
from urllib.parse import quote

# start user variables section

server_name = 'xxxxxxxx'
token = 'xxxxxxxxxxxxxxxxxxxx'
library_number = ##

tag_delimiter = ";"
skip_artists = ['Various Artists']
style_source = "grouping" # genre, grouping, or none
style_fallback = "genre" # remove, ignore, or genre
genre_fallback = "remove" # remove or ignore
verbose_mode = False
lock_albums = True
lock_artists = True
path_aliases = []

# end user variables section

parser = argparse.ArgumentParser()
parser.add_argument('-range', nargs='?', default='',  help='date range or start date')
parser.add_argument('-search', nargs='?', default='', help='artist or album search string')
parser.add_argument('-genre', nargs='?', default='', help='genre search string')
parser.add_argument('-index', nargs='?', default=0, help='starting index (for resuming)')
parser.add_argument('-simulate', nargs='?', default=False, help='don\'t write changes to plex')
parser.add_argument('-repair', nargs='?', default=False, help='only change artists with mismatched style/genre count or no genres/styles')
args = parser.parse_args()
search_string = args.search
genre_string = args.genre
date_range = args.range
starting_index = int(args.index)
simulate_changes = str(args.simulate).lower() in ['True', '1', 'yes']
repair_mode = str(args.repair).lower() in ['True', '1', 'yes']

# this mode depends on the output of "backup-albums.py", allowing faster scanning of the entire library in repair mode, contact me for early access
use_csv_backup = False 

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
artist_styles = []
album_styles = []
j = 0;
print("\n")

# print("using filters: ",plex_filters)

if repair_mode:
  if style_source == "genre":
    print("Repair mode: only artists/albums whose genre/style counts mismatch or are 0 will be updated\n")
  else:
    print("Repair mode: only artists/albums with 0 genres/styles will be updated\n")

try:

  if(search_string != '' or date_range != '' or use_csv_backup == False):

    # check recently added artists and albums
    for artist in tqdm(library.search(sort="titleSort:asc",filters=plex_filters,libtype='artist'), desc="Looking for Artists"):
      selected_artists.setdefault(artist.key,artist.title)
      
    for album in tqdm(library.search(sort="artist.titleSort:asc",filters=plex_filters,libtype='album'), desc="Looking for Albums"):
      if not album.parentTitle in skip_artists:
        selected_artists.setdefault(album.parentKey,album.parentTitle)
      else:
        # for skip_artists matches, add albums individually to avoid refreshing all albums
        selected_artists.setdefault(album.parentKey,album.parentTitle)
        skipped_artist_albums.setdefault(album.parentTitle, {})
        skipped_artist_albums[album.parentTitle].setdefault(album.key,album.title)
    
  if use_csv_backup == True and not (search_string != '' or date_range != ''):
    print("CSV mode: using data saved from backup-artists.py\n")
    # load csv data (from backup-artists.py)
    artist_dict = pd.read_csv("plex-artist-data.csv", index_col='artist').T.to_dict()
    selected_artists = dict([(k, v['title']) for (k,v) in artist_dict.items()])
    # print(selected_artists)
    
  if starting_index > len(selected_artists):
    starting_index = 0
    tqdm.write("Starting index out of range. Starting from 0.")
    
  for (artist_key,artist_title) in tqdm(list(selected_artists.items())[starting_index:], desc="Scanning Tags", total=len(selected_artists),initial=starting_index):

    j = 0
    if(search_string != '' or date_range != '' or use_csv_backup == False):
      artist = library.fetchItem(artist_key)
      artist.reload()
      time.sleep(2)
    else:
      # check genre/style count from csv to speed up repair mode
      artist = SimpleNamespace()
      csv_artist = artist_dict[artist_key]
      artist.genres = csv_artist['genres'].split(", ")
      artist.styles = csv_artist['styles'].split(", ")
      artist.title = csv_artist['title']

    artist_genres.clear()
    artist_styles.clear()
    
    try:
      
      if not repair_mode or ((len( artist.genres) != len( artist.styles)) and style_source == "genre") or len( artist.genres) == 0:
      
        tqdm.write("┌ Scanning: "+str(artist_title))
        
        if not artist.title in skip_artists:
          # switch back to plex source if using csv backup
          if use_csv_backup == True:
            artist = library.fetchItem(artist_key)
            artist.reload()
            time.sleep(2)
          # add all artist albums to selected_albums
          selected_albums = artist.albums()
        else:
          # for skip_artists matches, add skipped_artist_albums to selected_albums so they get processed
          selected_albums = []
          if verbose_mode:
            tqdm.write('│  Filter includes: '+str([v for (k,v) in skipped_artist_albums[artist_title].items()]))
          for k in skipped_artist_albums[artist_title]:
            album = library.fetchItem(k)
            if not repair_mode or ((len(album.genres) != len(album.styles)) and style_source == "genre") or len(album.genres) == 0:
              selected_albums.append(album)
        
        tqdm.write('│  Found '+str(len(selected_albums))+' albums:')

        # for each album
        for album in selected_albums:
        
          # delay scan to prevent errors
          time.sleep(1)

          album_genres.clear()
          album_styles.clear()

          tqdm.write("│ ┌ Scanning: "+str(album.title))
          
          # get filename and adjust drive/path aliases
          file = str(album.tracks()[0].media[0].parts[0].file).replace(baseurl,'')
          for alias in path_aliases:
            file = file.replace(alias[0], alias[1])
            
          if verbose_mode:
            tqdm.write("│ │   Source: "+file)
          j = j+1
          
          try:
            # extract genre tags
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
                    
              # extract grouping (TIT1) tags
              if style_source == "grouping":
                adv_tags = mutagen.File(file)
                style_list = []
                tag_location = ''
                # check for various tag locations
                if 'contentgroup' in adv_tags:
                  tag_location = 'contentgroup'
                if 'TIT1' in adv_tags:
                  tag_location = 'TIT1'
                if 'grouping' in adv_tags:
                  tag_location = 'grouping'
                # iterate through grouping tags
                if not tag_location == '':
                  for tag in adv_tags[tag_location]:
                    style_list.append(tag)
                if len(style_list) > 0:
                  # add album styles to artist styles list
                  for style in style_list:
                    if tag_delimiter in style:
                      style_split = style.split(tag_delimiter)
                      for gs in style_split:
                        if not gs in album_styles:
                          album_styles.append(gs.strip())
                          artist_styles.append(gs.strip())
                    else:
                      if not style in album_styles:
                        album_styles.append(style.strip())
                      if not style in artist_styles:
                        artist_styles.append(style.strip())

              # list genres for album
              album_glist = list(dict.fromkeys(album_genres))
              album_changes.append([artist.title+' - '+album.title,album.key,album_glist])
              tqdm.write("│ │   Genres: "+str(album_glist))

              # list styles for album
              if style_source == "grouping":
                album_slist = list(dict.fromkeys(album_styles))
                album_changes.append([artist.title+' - '+album.title,album.key,album_slist])
                if len(album_slist) > 0:
                  tqdm.write("│ │   Styles: "+str(album_slist))

              # clear existing genres
              if hasattr(album,'genres') and album.genres and (len(album_glist) > 0 or genre_fallback == "remove"):
                if verbose_mode:
                  tqdm.write("│ │ Removing: "+str([genre.tag for genre in album.genres])+" from genres")
                gcount = len(album.genres)
                if not simulate_changes:
                  album.removeGenre([genre.tag for genre in album.genres], False)
                  time.sleep(1)

              # clear existing styles
              if (style_source == "grouping" and len(album_slist) > 0) or (style_fallback == "genre" and len(album_glist) > 0) or style_fallback == "remove":
                scount = 0
                if hasattr(album,'styles') and album.styles:
                  if verbose_mode:
                    tqdm.write("│ │ Removing: "+str([style.tag for style in album.styles])+" from styles")
                  scount = len(album.styles)
                  if not simulate_changes:
                    album.removeStyle([style.tag for style in album.styles], False)
                    time.sleep(1)

              # make album changes
              try:
                album_direct = library.fetchItem(album.key)
                if verbose_mode:
                  tqdm.write('│ │  Adding: '+str(album_glist))
                if style_source == "genre" and len(album_glist) > 0:
                  if not simulate_changes:
                    album_direct.editTags("genre", album_glist, album_lock_bit).editTags("style", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres/styles")
                elif (style_source == "grouping" and len(album_slist) > 0) or (len(album_glist) > 0 and style_fallback == "genre"):
                  if not simulate_changes:
                    if len(album_slist) > 0:
                      album_direct.editTags("genre", album_glist, album_lock_bit).editTags("style", album_slist, album_lock_bit)
                    else: 
                      # genre fallback
                      album_direct.editTags("genre", album_glist, album_lock_bit).editTags("style", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres & "+str(len(album_slist))+" styles")
                elif len(album_glist) > 0:
                  if not simulate_changes:
                    album_direct.editTags("genre", album_glist, album_lock_bit)
                  tqdm.write("│ └    Added: "+str(len(album_glist))+" genres")
                time.sleep(1)
                
              except PlexApiException as err:
                tqdm.write('│ └    Server Error: '+str(err))
                  
              gcount = 0
              scount = 0
              
            else:
             tqdm.write("│ └    Error: no genre tags found")
             
            time.sleep(2)

          except MutagenError as e:
            tqdm.write("│ └    Error: "+str(str(e).split(";")[0]))
        
        # list tags for artist
        artist_glist = list(dict.fromkeys(artist_genres))
        artist_changes.append([artist.title,artist.key,artist_glist])

        # list styles for artist
        artist_slist = list(dict.fromkeys(artist_styles)) if style_source == "grouping" else list(dict.fromkeys(artist_genres))

        # make artist changes
        if not artist_title in skip_artists:
        
          try:
            artist_changed = False
            
            # remove existing artist genres
            if hasattr(artist,'genres') and artist.genres and (len(artist_glist) > 0 or genre_fallback == "remove"):
              if verbose_mode:
                tqdm.write("│ Removing: "+str([genre.tag for genre in artist.genres])+" from genres")
              if not simulate_changes:
                artist.removeGenre([genre.tag for genre in artist.genres], False)
                artist_changed == True

            # remove existing artist styles
            if (style_source == "grouping" and len(artist_slist) > 0) or (style_fallback == "genre" and len(artist_glist) > 0) or style_fallback == "remove":
              if hasattr(artist,'styles') and artist.styles:
                if verbose_mode:
                  tqdm.write("│ Removing: "+str([style.tag for style in artist.styles])+" from styles")
                if not simulate_changes:
                  artist.removeStyle([style.tag for style in artist.styles], False)
                  artist_changed == True
                  
            # slow down plex scanning
            if artist_changed:
              time.sleep(1)
              artist.reload()

            if verbose_mode:
              tqdm.write('│   Adding: '+str(artist_glist))
              
            # update styles
            if style_source == "genre" and len(artist_glist) > 0:
              if not simulate_changes:
                # styles set from genre
                artist.editTags("genre", artist_glist, artist_lock_bit).editTags("style", artist_glist, artist_lock_bit)
              tqdm.write("│    Added: "+str(len(artist_glist))+" genres/styles")
            elif (style_source == "grouping" and len(artist_slist) > 0) or (len(artist_glist) > 0 and style_fallback == "genre"):
              if not simulate_changes:
                if len(artist_slist) > 0:
                  # styles set from grouping
                  artist.editTags("genre", artist_glist, artist_lock_bit).editTags("style", artist_slist, artist_lock_bit)
                else: 
                  # genre fallback
                  artist.editTags("genre", artist_glist, artist_lock_bit).editTags("style", artist_glist, artist_lock_bit)
              tqdm.write("│    Added: "+str(len(artist_glist))+" genres & "+str(len(artist_slist))+" styles")
            elif len(artist_glist) > 0:
              if not simulate_changes:
                # styles left empty
                artist.editTags("genre", artist_glist, artist_lock_bit)
              tqdm.write("│   Added: "+str(len(artist_glist))+" genres")
              
          except PlexApiException as err:
            collect_errors.append("Server Error: "+str(err))
            tqdm.write('│    Error: '+str(err))
            
        else:
          tqdm.write("│ Skipping: "+str(artist.title))
          
      else:
      
        # slow down plex scanning
        if use_csv_backup == False:
          time.sleep(1)

    except requests.exceptions.RequestException as err:
      collect_errors.append("Connection Error: "+str(err))
      tqdm.write('│  Error: '+str(err))

    if j > 0:
      tqdm.write("└ "+(str(j)+" albums checked for "+artist.title)+"\n")
    
except requests.exceptions.RequestException as err:
  collect_errors.append("Connection Error: "+str(err))
  tqdm.write('│  Error: '+str(err))

print("\n"+str(len(artist_changes)),("artists" if len(artist_changes) > 1 else "artist"),"had",("genres/styles" if not style_source == 'none' else "genres"),"updated from "+str(len(album_changes))+' albums')

if len(collect_errors) > 0:
  print("Errors: ",len(collect_errors))
