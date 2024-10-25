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
import os
from urllib.parse import quote
os.environ["PLEXAPI_PLEXAPI_CONTAINER_SIZE"] = "100"
os.environ["PLEXAPI_PLEXAPI_TIMEOUT"] = "60"

# start user variables section

server_name = 'xxxxxxxx'
token = 'xxxxxxxxxxxxxxxxxxxx'
library_number = ##

tag_delimiter = ";"
skip_artists = ['Various Artists']
album_only_tags = ['Christmas','Multichannel']
style_source = "genre" # genre, none ("grouping" may still work, untested for a while)
style_fallback = "genre" # remove, ignore, or genre
genre_fallback = "remove" # remove or ignore
preserve_order = True # faster if False but new tags are added to the end of the list
lock_albums = True
lock_artists = True
path_aliases = []
path_prepend = ''

# end user variables section

parser = argparse.ArgumentParser()
parser.add_argument('-range', nargs='?', default='',  help='date range or start date')
parser.add_argument('-search', nargs='?', default='', help='artist or album search string')
parser.add_argument('-genre', nargs='?', default='', help='search for specific genre (by #)')
parser.add_argument('-style', nargs='?', default='', help='search for specific style (by #)')
parser.add_argument('-index', nargs='?', default=0, help='starting index (for resuming)')
parser.add_argument('-limit', nargs='?', default=999999, help='only process n artists')
parser.add_argument('-simulate', nargs='?', default=False, help='don\'t write changes to plex')
parser.add_argument('-verbose', nargs='?', default=False, help='display extra console information')
parser.add_argument('-csv', nargs='?', default=False, help='use csv data instead of plex connection')
parser.add_argument('-repair', nargs='?', default=False, help='only update albums with mismatched style/genre count or no genres/styles')
parser.add_argument('-albumsonly', nargs='?', default=False, help='only change album tags')
parser.add_argument('-artistsonly', nargs='?', default=False, help='only change artist tags')
args = parser.parse_args()
search_string = args.search
genre_string = args.genre
style_string = args.style
date_range = args.range
artist_limit = int(args.limit)
starting_index = int(args.index)
simulate_changes = str(args.simulate).lower() in ['true', '1', 'yes']
repair_mode = str(args.repair).lower() in ['true', '1', 'yes']
albums_only = str(args.albumsonly).lower() in ['true', '1', 'yes']
artists_only = str(args.artistsonly).lower() in ['true', '1', 'yes']
verbose_mode = str(args.verbose).lower() in ['true', '1', 'yes']
use_csv_backup = str(args.csv).lower() in ['true', '1', 'yes']

account = MyPlexAccount(token=token)
plex = account.resource(server_name).connect()
library = plex.library.sectionByID(library_number)

# only lock styles if enabled - plex fixed genre scanning
album_lock_bit = 1 if lock_albums else 0
artist_lock_bit = 1 if lock_artists else 0


plex_filters = {"title": search_string, "addedAt>>": date_range} if date_range != '' else {"title": search_string}
if not genre_string == "":
  plex_filters['genre'] = genre_string
if not style_string == "":
  plex_filters['style'] = style_string
baseurl = str(plex._baseurl).replace('https://','')
selected_artists = collections.OrderedDict()
skipped_artist_albums = collections.OrderedDict()
total_artist_changes = set()
artist_album_changes = []
collect_errors = []
artist_genres = []
album_genres = []
artist_styles = []
album_styles = []
total_album_changes = 0;

# print("using filters: ",plex_filters)

if repair_mode:
  if style_source == "genre":
    print("\nRepair mode: only albums whose genre/styles mismatch or are 0 will be updated\n")
  else:
    print("\nRepair mode: only albums with 0 genres or 0 styles will be updated\n")

main_timer = time.perf_counter()



if use_csv_backup == True:
  print("CSV mode: using data saved from backup-artists.py and backup-albums.py\n")
  # load csv data (from backup-artists.py)
  artist_dict = pd.read_csv("plex-artist-data.csv", index_col='artist', low_memory=False).sort_values(by=['addedAt'],ascending=False).T.to_dict()
  albums_dict = pd.read_csv("plex-album-data.csv", index_col='album', low_memory=False).sort_values(by=['originallyAvailableAt'],ascending=False).T.to_dict()
  # filter csv results (better way to do this?)
  if search_string != '':
    selected_artists = dict([("/library/metadata/"+str(k), v['title']) for (k,v) in artist_dict.items() if search_string.lower() in v['title'].lower()])
  else:
    selected_artists = dict([("/library/metadata/"+str(k), v['title']) for (k,v) in artist_dict.items()])

  # print(artist_dict)
  # print(selected_artists)

if(date_range != '' or genre_string != '' or style_string != '' or use_csv_backup == False):


  # check recently added artists and albums
  search_timer = time.perf_counter()
  print("Searching for Artists...")
  for artist in library.search(sort="titleSort:asc",filters=plex_filters,libtype='artist'):
    selected_artists.setdefault(artist.key,artist.title)
  print("Searching for Albums...")
  # remove search string for album search
  plex_filters['title'] = ''
  for album in library.search(sort="artist.titleSort:asc",filters=plex_filters,libtype='album'):
    if search_string.lower() in album.parentTitle.lower():
      if not album.parentTitle in skip_artists:
        selected_artists.setdefault(album.parentKey,album.parentTitle)
      else:
        # for skip_artists (various artists) matches, add albums individually to avoid refreshing all albums
        selected_artists.setdefault(album.parentKey,album.parentTitle)
        # print('adding',album.title)
        skipped_artist_albums.setdefault(album.parentTitle, {})
        skipped_artist_albums[album.parentTitle].setdefault(album.key,album.title)
  tqdm.write("Search complete ["+str(round(time.perf_counter()-search_timer,2))+"s]")


if starting_index > len(selected_artists):
  starting_index = 0
  print("Starting index out of range. Starting from 0.\n")
  
tqdm.write('Found '+str(len(selected_artists))+' artists')

for (artist_key,artist_title) in tqdm(list(selected_artists.items())[starting_index:artist_limit], desc="Scanning Artists", total=len(selected_artists),initial=starting_index, position=1, leave=False):

  # album_change_counter = 0
  if(search_string != '' or date_range != '' or genre_string != '' or style_string != '' or use_csv_backup == False):
    artist = library.fetchItem(artist_key)
    # artist.reload()
    # time.sleep(2)
  else:
    # check genre/style count from csv to speed up repair mode
    artist = SimpleNamespace()
    csv_artist = artist_dict[int(artist_key.replace("/library/metadata/",""))]
    artist_genre_tags = []
    for tag in csv_artist['genres'].split(", ") if ", " in csv_artist['genres'] else csv_artist['genres']:
      tag_object = SimpleNamespace()
      tag_object.tag = tag.strip("\"' ")
      artist_genre_tags.append(tag_object)
    artist.genres = artist_genre_tags
    artist_style_tags = []
    for tag in csv_artist['styles'].split(", ") if ", " in csv_artist['styles'] else csv_artist['styles']:
      tag_object = SimpleNamespace()
      tag_object.tag = tag.strip("\"' ")
      artist_style_tags.append(tag_object)
    artist.styles = artist_style_tags
    artist.title = csv_artist['title']

    # tqdm.write(str(artist.genres))
    # tqdm.write(str(artist.styles))


  artist_genres.clear()
  artist_styles.clear()

  try:
    
    artist_timer = time.perf_counter()
    tqdm.write("┌  Scanning: "+str(artist_title))
    
    if verbose_mode:
      tqdm.write("│  Artist key: "+artist.key)
    
    selected_albums = []
    if not artist_title in skip_artists or search_string.lower() == artist_title.lower():
      if use_csv_backup == True:
        selected_albums = [(k, v) for (k,v) in albums_dict.items() if v['parentKey'] == artist_key]
      else:
        # add all artist albums to selected_albums

        for a in artist.albums():
          album = library.fetchItem(a.key)
          selected_albums.append(album)
      
    else:
      # for skip_artists matches, add skipped_artist_albums to selected_albums so they get processed
      
      if verbose_mode:
        tqdm.write('│  Filter includes: '+str([v for (k,v) in skipped_artist_albums[artist_title].items()]))
      if artist_title in skipped_artist_albums:
        # print(artist_title,len(skipped_artist_albums[artist_title]))
        for k in skipped_artist_albums[artist_title]:
          album = library.fetchItem(k)
          # if not repair_mode or ((len(album.genres) != len(album.styles)) and style_source == "genre") or not album.genres:
          selected_albums.append(album)
      else:
        tqdm.write('│ └ Skipping: no albums to check')

  
    tqdm.write('│  Found '+str(len(selected_albums))+' albums')

    # tqdm.write(str(selected_albums))
    
    artist_album_changes = []
        
    album_tqdm = tqdm(selected_albums, desc="└  Scanning Albums", position=0, leave=False)
    album_timer = time.perf_counter()
    
    for album_item in album_tqdm:
    
      # tqdm.write(str(album_item))

      
      # if not simulate_changes:
        # album.batchEdits()

      if use_csv_backup:
      
        csv_album = albums_dict[album_item[1]['key']]
        album = SimpleNamespace()
        album.genres = csv_album['genres'][1:-1]
        album.styles = csv_album['styles'][1:-1]
        album.title = csv_album['title']
        ag_string = str(album.genres)
        as_string = str(album.styles)
        
      else:
      
        album = album_item
        ag_string = str(list(map(lambda o : o.tag, album.genres)))
        as_string = str(list(map(lambda o : o.tag, album.styles)))
        
      # tqdm.write(ag_string)
      # tqdm.write(as_string)
        
       
      album_genres.clear()
      album_styles.clear()

      tqdm.write("│ ┌  Scanning: "+str(album.title))

      if not repair_mode or (len(ag_string) != len(as_string) and style_source == "genre") or (not hasattr(album,'genres') or len(album.genres) == 0 or album.genres[0] == ''):

        # connect to plex album
        if use_csv_backup:
          album = library.fetchItem(album_item[1]['key'])

        if verbose_mode:
          tqdm.write("│ │   Album key: "+album.key)

        # get filename and adjust drive/path aliases
        file = str(album.tracks()[0].media[0].parts[0].file).replace(baseurl,'')
        for alias in path_aliases:
          file = file.replace(alias[0], alias[1])
        file = path_prepend + file
        
        if verbose_mode:
          tqdm.write("│ │   Source: "+file)
        # album_change_counter = album_change_counter+1
        
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
                    if not gs in album_only_tags:
                      artist_genres.append(gs.strip())
              else:
                if not genre in album_genres:
                  album_genres.append(genre.strip())
                if not genre in artist_genres:
                  if not genre in album_only_tags:
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
                        if not gs in album_only_tags:
                          artist_styles.append(gs.strip())
                  else:
                    if not style in album_styles:
                      album_styles.append(style.strip())
                    if not style in artist_styles:
                      if not style in album_only_tags:
                        artist_styles.append(style.strip())

            # list genres for album
            album_glist = list(dict.fromkeys(album_genres))
            if verbose_mode:
              tqdm.write("│ │   File genres: "+str(album_glist))
            if verbose_mode:
              tqdm.write("│ │   Plex genres: "+str([str(genre.tag) for genre in album.genres]))

            # list styles for album
            if style_source == "grouping":
              album_slist = list(dict.fromkeys(album_styles))
              if len(album_slist) > 0:
                tqdm.write("│ │   File styles: "+str(album_slist))
            if verbose_mode:
              tqdm.write("│ │   Plex styles: "+str([str(style.tag) for style in album.styles]))

            # if not repair_mode or ((len( album.genres) != len( album.styles)) and style_source == "genre") or len(album.genres) == 0 or len(album.styles) == 0:
            
            # start = time.perf_counter()
            # make album changes
            try:
                          

              # find tags to remove
              if preserve_order:
                genres_to_remove = [str(genre.tag) for genre in album.genres] if not [tag.lower() for tag in album_glist] == [str(genre.tag).lower() for genre in album.genres] else []
                if 'album_slist' in locals():
                  styles_to_remove = [str(style.tag) for style in album.styles] if not [tag.lower() for tag in album_slist] == [str(style.tag).lower() for style in album.styles] else []
                else:
                  styles_to_remove = [str(style.tag) for style in album.styles] if not [tag.lower() for tag in album_glist] == [str(style.tag).lower() for style in album.styles] else []
              else:
                genres_to_remove = [str(genre.tag) for genre in album.genres if genre.tag.lower() not in [tag.lower() for tag in album_glist]]
                if style_source == "grouping":
                  styles_to_remove = [str(style.tag) for style in album.styles if style.tag.lower() not in [tag.lower() for tag in album_slist]]
                else:
                  styles_to_remove = [str(style.tag) for style in album.styles if style.tag.lower() not in [tag.lower() for tag in album_glist]]
                
              # tqdm.write(str(genres_to_remove))
              # tqdm.write(str(styles_to_remove))
              
              if len(genres_to_remove) or len(styles_to_remove):
                # album = library.fetchItem(album.key)
                if verbose_mode:
                  tqdm.write("│ │  Starting album edit...")
                if not simulate_changes and not artists_only:
                  album.batchEdits()

              # clear existing genres
              if len(genres_to_remove) and hasattr(album,'genres') and album.genres and (len(album_glist) or genre_fallback == "remove"):
                gcount = len(album.genres)
                if verbose_mode:
                  tqdm.write("│ │  Clearing album genres...")
                if not artists_only:
                  if verbose_mode:
                    tqdm.write("│ │  Removed: "+str(genres_to_remove)+" from genres")
                  if not simulate_changes:
                    album.removeGenre(genres_to_remove, False)
                  
              # clear existing styles
              #if len(styles_to_remove) and (style_source == "grouping" and len(album_slist)) or (style_fallback == "genre" and len(album_glist)) or style_fallback == "remove":
              if len(styles_to_remove) and ((style_source == "grouping" and len(album_slist)) or (style_fallback == "genre" and len(album_glist)) or style_fallback == "remove"):
                scount = 0
                if verbose_mode:
                  tqdm.write("│ │  Clearing album styles...")
                if hasattr(album,'styles') and album.styles:
                  scount = len(album.styles)
                  if not artists_only:
                    if verbose_mode and len(styles_to_remove):
                      tqdm.write("│ │  Removed: "+str(styles_to_remove)+" from styles")
                    if not simulate_changes:
                      album.removeStyle(styles_to_remove, album_lock_bit)

              # write album changes
              if not artists_only and (len(genres_to_remove) or len(styles_to_remove)):
                tqdm.write("│ │  Updating album...")
                try:
                  if not simulate_changes:
                    album.saveEdits()
                except requests.exceptions.RequestException as err:
                  collect_errors.append("Connection Error: "+str(err))
                  tqdm.write('│  Error: '+str(err))
                  continue
          
              # fetch album again to prevent removed tags from reappearing (api bug?)
              if use_csv_backup and not (simulate_changes and artists_only):
                album = library.fetchItem(album_item[1]['key'])
              else:
                album = library.fetchItem(album.key)


              # find tags to add
              genres_to_add = [tag for tag in album_glist if tag.lower() not in [str(genre.tag.lower()) for genre in album.genres]]
              if style_source == "grouping":
                styles_to_add = [tag for tag in album_slist if tag.lower() not in [str(style.tag.lower()) for style in album.styles]]
              else:
                styles_to_add = [tag for tag in album_glist if tag.lower() not in [str(style.tag.lower()) for style in album.styles]]

              # restart batch edit
              if not artists_only and (len(genres_to_add) or len(genres_to_add)):
                if verbose_mode:
                  tqdm.write("│ │  Restarting album edit...")
                if not simulate_changes:
                  album.batchEdits()
            
              if len(genres_to_add):
                if verbose_mode:
                  tqdm.write('│ │  Adding genres: '+str(genres_to_add))
                artist_album_changes.append([artist.title+' - '+album.title,album.key,genres_to_add])
                if not simulate_changes and not artists_only:
                  album.editTags("genre", genres_to_add, 0)
                tqdm.write("│ │  Added "+str(len(genres_to_add))+" genres")
              
              if len(styles_to_add) and not artists_only:
                if verbose_mode:
                  tqdm.write('│ │  Adding styles: '+str(styles_to_add))
                  
                if not len(genres_to_add):
                  artist_album_changes.append([artist.title+' - '+album.title,album.key,styles_to_add])
                
                if (style_source == "grouping" and len(styles_to_add) > 0) or (len(genres_to_add) > 0 and style_fallback == "genre"):
                  if not simulate_changes and not artists_only:
                    if len(styles_to_add):
                      album.editTags("style", styles_to_add, album_lock_bit)
                    else: 
                      # genre fallback
                      album.editTags("style", genres_to_add, album_lock_bit)
                else:
                  if not simulate_changes:
                    album.editTags("style", styles_to_add, album_lock_bit)
                    
                tqdm.write("│ │  Added "+str(len(styles_to_add))+" styles")

              # update album change count
              total_album_changes = total_album_changes + len(artist_album_changes)
              
              # write album changes
              if not artists_only and (len(genres_to_add) or len(genres_to_add)):
                if verbose_mode:
                  tqdm.write("│ │  Updating album...")
                try:
                  if not simulate_changes:
                    album.saveEdits()
                except requests.exceptions.RequestException as err:
                  collect_errors.append("Connection Error: "+str(err))
                  tqdm.write('│  Error: '+str(str(err).split(": ")[1] if len(str(err).split(": ")) else err))
                  continue
              
              if not len(styles_to_add) and not len(styles_to_add):
                tqdm.write("│ └  No changes needed")
              else:
                tqdm.write("│ └  Album updated")
              
            except PlexApiException as err:
              tqdm.write('│ └  Server Error: '+str(str(err).split(": ")[1] if len(str(err).split(": ")) else err))
                
            gcount = 0
            scount = 0

            
          else:
           tqdm.write("│ └  Error: no genre tags found")
           
          # slow down plex scanning
          # if use_csv_backup == False:
            # time.sleep(1)

        except MutagenError as e:
          tqdm.write("│ └  Error: "+str(str(e).split(";")[0]))

      # catch albums that didn't need repair - only store tags for artist check
      else:
        if repair_mode:
        
          # if use_csv_backup:
          
          # tqdm.write(str(album.genres))
          # tqdm.write(str(album.styles))
          
          # album_change_counter = album_change_counter+1
          # list genres for album
          album_glist = [g.tag.strip("\"' ") if len(g.tag) else '' for g in album.genres]
          for tag in album_glist:
            if not tag.strip("\"' ") in album_only_tags:
              artist_genres.append(tag.strip("\"' "))
          if verbose_mode:
            tqdm.write("│ │   Plex genres: "+str(album_glist))

          # list styles for album
          if style_source == "grouping":
            album_slist = [s.tag.strip("\"' ") if len(s.tag) else '' for s in album.styles] if len(album.styles) else []
            for tag in album_slist:
              if not tag.strip("\"' ") in album_only_tags:
                artist_styles.append(tag.strip("\"' "))
            # artist_album_changes.append([artist.title+' - '+album.title,album.key,album_slist])
            if len(album_slist) > 0 and verbose_mode:
              tqdm.write("│ │   Plex styles: "+str(album_slist))
            
          tqdm.write('│ └  No repair needed')
          
          # tqdm.write(str(artist_genres))
          # tqdm.write(str(artist_styles))


    # if not simulate_changes:
      # try:
        # album.saveEdits()
      # except requests.exceptions.RequestException as err:
        # collect_errors.append("Connection Error: "+str(err))
        # tqdm.write('│  Error: '+str(err))
        # continue
    
    # tqdm.write("│  Albums checked ["+str(round(time.perf_counter()-album_timer,2))+"s]")
    if len(artist_album_changes) > 0 or repair_mode:
      tqdm.write("│  "+str(len(artist_album_changes))+" albums updated ["+str(round((time.perf_counter()-album_timer),2))+"s]")
    else:
      tqdm.write("│  All albums skipped ["+str(round((time.perf_counter()-album_timer),2))+"s]")

    album_tqdm.clear()
    
    # collect tags for artist (from albums)
    artist_glist = list(dict.fromkeys(artist_genres))
    artist_slist = list(dict.fromkeys(artist_styles)) if style_source == "grouping" else list(dict.fromkeys(artist_genres))

    # tqdm.write(str(artist.genres))
    # tqdm.write(str(artist.styles))
    

    # make artist changes
    if not artist_title in skip_artists and not albums_only and (not repair_mode or len(str(list(map(lambda o : o.tag, artist.genres)))) != len(str(list(map(lambda o : o.tag, artist.styles)))) or (not hasattr(artist,'genres') or len(artist.genres) == 0 or artist.genres[0] == '')):
    
      try:
        artist_changed = False
        
        # find tags to remove
        if preserve_order:
          genres_to_remove = [str(genre.tag) for genre in artist.genres] if [tag.lower() for tag in artist_glist] != [str(genre.tag).lower() for genre in artist.genres] else []
          styles_to_remove = [str(style.tag) for style in artist.styles] if [tag.lower() for tag in artist_slist] != [str(style.tag).lower() for style in artist.styles] else []
        else:
          genres_to_remove = [str(genre.tag) for genre in artist.genres if genre.tag not in [tag.lower() for tag in artist_glist]]
          styles_to_remove = [str(style.tag) for style in artist.styles if style.tag not in [tag.lower() for tag in artist_glist]]

        # tqdm.write(str(genres_to_remove))
        # tqdm.write(str(styles_to_remove))

        if len(genres_to_remove) > 0 or len(styles_to_remove) > 0 or len(artist.genres) == 0 or len(artist.styles) == 0:
          tqdm.write("│  Updating artist...")
          total_artist_changes.add(artist.title)
          # connect to plex artist
          if use_csv_backup:
            artist = library.fetchItem(artist_key)
            
          start = time.perf_counter()
          # start = time.perf_counter()
          # remove extra artist genres
          if len(genres_to_remove) > 0 and hasattr(artist,'genres') and artist.genres and (len(artist_glist) > 0 or genre_fallback == "remove"):
            # remove_tags = [genre.tag for genre in artist.genres]
            if not simulate_changes:
              artist.removeGenre(genres_to_remove, False)
              # artist.editTags("genre", remove_tags, remove=True)
              artist_changed = True
            if verbose_mode:
              tqdm.write("│  Removed: "+str(genres_to_remove)+" from genres")
            # else:
              # tqdm.write("│  Removed: "+str(len([genre.tag for genre in artist.genres]))+" genres ("+str(round(time.perf_counter()-start,2))+"s)")

          # remove existing artist styles
          if (len(styles_to_remove) > 0 and ((style_source == "grouping" and len(artist_slist) > 0) or (style_fallback == "genre" and len(artist_glist) > 0) or style_fallback == "remove")):
            if hasattr(artist,'styles') and artist.styles:
              # remove_tags = [style.tag for style in artist.styles]
              if not simulate_changes:
                artist.removeStyle(styles_to_remove, artist_lock_bit)
                # artist.editTags("style", remove_tags, remove=True)
                artist_changed = True
              if verbose_mode:
                tqdm.write("│  Removed: "+str(styles_to_remove)+" from styles")
              # else:
                # tqdm.write("│  Removed: "+str(len([style.tag for style in artist.styles]))+" styles ("+str(round(time.perf_counter()-start,2))+"s)")

        if artist_changed:
          time.sleep(1)
          artist.reload()

        # find tags to add
        if preserve_order:
          genres_to_add = [genre for genre in artist_glist] if not [tag.lower() for tag in artist_glist] == [str(genre.tag).lower() for genre in artist.genres] else []
          if style_source == "grouping":
            styles_to_add = [style for style in artist_slist] if not [tag.lower() for tag in artist_slist] == [str(genre.tag).lower() for genre in artist.genres] else []
          else:
            # take styles from genres
            styles_to_add = [style for style in artist_glist] if not [tag.lower() for tag in artist_glist] == [str(style.tag).lower() for style in artist.styles] else []
        else:
          genres_to_add = [genre for genre in artist_glist if genre.lower() not in [str(genre.tag).lower() for genre in artist.genres]]
          if style_source == "grouping":
            styles_to_add = [style for style in artist_slist if style.lower() not in [str(style.tag).lower() for style in artist.styles]]
          else:
            # take styles from genres
            styles_to_add = [style for style in artist_glist if style.lower() not in [str(style.tag).lower() for style in artist.styles]]

        if len(genres_to_add) > 0 or len(styles_to_add) > 0:
          # connect to plex artist
          if use_csv_backup:
            artist = library.fetchItem(artist_key)

          total_artist_changes.add(artist.title)
          if verbose_mode:
            tqdm.write('│  Adding: '+str(artist_glist))

          # update genres & styles
          if len(genres_to_add) > 0 and len(styles_to_add) > 0:
            if not simulate_changes:
              artist.editTags("genre", genres_to_add, 0).editTags("style", styles_to_add, artist_lock_bit)
          elif len(genres_to_add) > 0:
            if not simulate_changes:
              artist.editTags("genre", genres_to_add, 0)
          elif len(styles_to_add) > 0:
            if not simulate_changes:
              artist.editTags("style", styles_to_add, artist_lock_bit)
          tqdm.write("│  Added "+str(len(genres_to_add))+" genres & "+str(len(styles_to_add))+" styles")
            
      except PlexApiException as err:
        collect_errors.append("Server Error: "+str(err))
        tqdm.write('│  Error: '+str(str(err).split(": ")[1] if ": " in str(err) else str(err)))
        
    else:
      if repair_mode:
        tqdm.write("│  No repair needed")
      else:
        tqdm.write("│  Skipping: "+str(artist.title))
      
  except requests.exceptions.RequestException as err:
    collect_errors.append("Connection Error: "+str(err))
    tqdm.write('└  Error: '+str(str(err).split(": ")[1] if ": " in str(err) else str(err)))
      
  if ('genres_to_add' in vars() and len(genres_to_add) > 0) or ('styles_to_add' in vars() and len(styles_to_add) > 0):
    tqdm.write("└  Artist updated ["+str(round((time.perf_counter()-artist_timer)/60,2))+"m]")
  else:
    tqdm.write("└  Artist unchanged ["+str(round((time.perf_counter()-artist_timer)/60,2))+"m]")

    
  if artist_limit == 999999:
    if artist_key != list(selected_artists.items())[starting_index:len(selected_artists.items())][-1][0]:
      tqdm.write(" ")
  else:
    if artist_key != list(selected_artists.items())[starting_index:artist_limit][-1][0]:
      tqdm.write(" ")
  

tqdm.write(" "+("Genres/styles" if not style_source == 'none' else "Genres")+" updated for "+str(len(total_artist_changes))+(" artists" if len(total_artist_changes) != 1 else " artist")+" and "+str(total_album_changes)+" albums ["+str(round((time.perf_counter()-main_timer)/60,2))+"m]")

if len(collect_errors) > 0:
  tqdm.write("Errors: "+str(len(collect_errors)))
