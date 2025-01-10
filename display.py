import datetime
from enum import Enum
import os
import threading
from typing import Dict, List
from urllib.parse import parse_qs, urlparse
import curses
import statistics
import numpy as np

import logs
from m3u8 import M3U8, DownloadMetrics
import m3u8

class Colors(Enum):
    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7

#in debug=True curses module is not used
_debug = False

_display_buffer_lines_limit = 1000
_display_buffer_lines: List[str] = []

# A lock object to ensure thread-safe printing
_global_print_lock = threading.Lock()

#curses._CursesWindow
_stdscr = None

_current_ipart: int = 0
_current_part = (0,0,0)
_processed_parts : List[int] = []
_last_line: int = -1
_line_counter: int = 1

_text_column_width = 29
_first_column_width = 45 + 4
_number_of_data_columns: int = 0

def check_for_dimming(item: tuple) -> bool:
    return item[2] == m3u8.TypeDownload.FILE_PART

## Define a thread-safe print function
def _safe_print(*args, **kwargs):
    with _global_print_lock:
        print(*args, **kwargs)

def _safe_print_curses(*args, **kwargs):
    with _global_print_lock:
        _safe_print_curses_internal(*args, **kwargs)

def _safe_print_curses_internal(text: str, item_to_add: tuple, media_index: int, force_new_line_if_not_empty: bool = False): 
    if _debug:
        return

    if _stdscr is None:
        return

    global _last_line
    global _processed_parts
    global _current_part
    global _display_buffer_lines
    global _display_buffer_lines_limit
    global _line_counter

    # Get the screen dimensions
    height, width = _stdscr.getmaxyx()   

    
    # if filename is already prined on the screen, then job has been done already
    text2 = ""
    found_item = find_or_nearest_tuple(_processed_parts, item_to_add)
    if found_item >= 0:
        if force_new_line_if_not_empty == False:
            return 
        else:
            # so it's force_new_line_if_not_empty == True
            x = _first_column_width + media_index * _text_column_width + 1 #48 27,  (4) is for counter
            if x >= width:
                # return, because we do not track values wich do not fit the screen, so nothing to print here
                return 
            line_from_bottom = len(_processed_parts) - found_item - 1 
            if _last_line < height:
                y = _last_line - line_from_bottom
            else:
                y = height - 1 - line_from_bottom 
            if y >= 0:  # and x < width
                text2 = _stdscr.instr(y, x, _text_column_width-1).decode().strip()
                if len(text2) == 0:
                    return


    ## Get the current cursor position
    #y, x = stdscr.getyx()

    # Determine the position for the text
    x = 0 
    y = 0   
    if _last_line < 0:
        y = 0
    else:
        y = _last_line
    
    ## Move to the y position just before the last line, scroll content up
    #stdscr.move(y, x)

    # If we are at the bottom of the screen, scroll the window
    if y == height - 1:
        text1 = _stdscr.instr(0, 0, curses.COLS).decode()
        _display_buffer_lines.append(text1)

        y -= 1 #because in the next step we increase a line again
        _stdscr.scroll(1)
    elif y > height - 1:
        for i in range(2):
            text1 = _stdscr.instr(i, 0, curses.COLS).decode()
            _display_buffer_lines.append(text1)

        y = height - 2 #because in the next step we increase a line again
        _stdscr.scroll(2)
        _stdscr.addstr(y, 0, "...")
        _processed_parts.clear()

    # keep in the buffer limited number of lines, so saving last N lines only
    if len(_display_buffer_lines) > _display_buffer_lines_limit:
        _display_buffer_lines = _display_buffer_lines[-_display_buffer_lines_limit:]

    # Move to the next line and print text
    y = y + 1
    _stdscr.move(y, 0)

    segmentnum, partnum, filetype = item_to_add
    text = f"{_line_counter:03d} {segmentnum:04d}-{partnum:02d} {datetime.datetime.now(datetime.UTC).strftime('%H:%M:%S.%f')[:-3]} {text}"
    _line_counter += 1

    tw_max = min(width-x-1, _first_column_width)

    #if file then change background for better visibility
    dim = curses.A_DIM if check_for_dimming(item_to_add) else 0
    _stdscr.addstr(y, x, text[:tw_max], curses.color_pair(0) | dim)

    # if check_for_dimming(item_to_add):
    #     # # Define original and darker background colors
    #     # original_bg = curses.COLOR_WHITE
    #     # darker_bg = 16  # The index for the new color, should be between 0 and 255
    #
    #     # # Get original RGB values
    #     # old_r, old_g, old_b = curses.color_content(original_bg)
    #     # h, l, s = colorsys.rgb_to_hls(old_r, old_g, old_b)
    #     # scale_l = 0.2
    #     # if l < 500:
    #     #     scale_l = 1 + scale_l
    #     # else:
    #     #     scale_l = 1 - scale_l
    #     # darker_color_r, darker_color_g, darker_color_b = colorsys.hls_to_rgb(h, max(min(l * scale_l, 1000.0),0.0), s)
    #     # # Reinit dark color
    #     # curses.init_color(darker_bg, int(darker_color_r), int(darker_color_g), int(darker_color_b))
    #       
    #     # # Initialize color pair with the new background
    #     # curses.init_pair(8, curses.COLOR_WHITE, darker_bg)
    #
    #     _stdscr.addstr(y, x, text[:tw_max], curses.A_DIM)  # curses.color_pair(8) Ensuring the text fits in the width
    # else:
    #     _stdscr.addstr(y, x, text[:tw_max])  # Ensuring the text fits in the width
    
    #_first_column_width
    for i in range (_number_of_data_columns+1):
        x = _first_column_width + i * _text_column_width #48 27,  (4) is for counter
        if x < width:
            _stdscr.addstr(y, x, "|")

    _stdscr.refresh()

    _current_part = item_to_add
    _processed_parts.append(item_to_add)

    _last_line = y

def _safe_print_curses_update_status(*args, **kwargs):
    with _global_print_lock:
        _safe_print_curses_update_status_internal(*args, **kwargs)

def _safe_print_curses_update_status_internal(item_to_find: tuple, text: str, status: str, status_color: Colors, metrics_tuple: tuple, media_index: int, force_new_line: bool = True): 
    if _debug:
        print(f"[{threading.current_thread().name}, index = {media_index} - {item_to_find} - {status}]")
        return

    global _processed_parts
    global _text_column_width
    global _first_column_width
    
    if _stdscr is None:
        return

    try:
        # scan the list descending: from bottom to top
        # -2 = didn't find it at all
        # -1 = did not find the specified element, but an older one has already been found
        # 0+ = element is found, exact position in the list is returned
        i = find_or_nearest_tuple(_processed_parts, item_to_find)
        if i == -2:
            return
        elif i == -1:
            return
        else:
            line_from_bottom = len(_processed_parts) - i - 1 #len(_processed_parts) - i - 1

        # Get the screen dimensions
        height, width = _stdscr.getmaxyx()    

        # Determine the position for the text

        x = _first_column_width + media_index * _text_column_width + 1 #48 27,  (4) is for counter
        if _last_line < height:
            y = _last_line - line_from_bottom
        else:
            y = height - 1 - line_from_bottom 
        if y < 0:
            return

        if force_new_line == True:
            if x < width: 
                text2 = _stdscr.instr(y, x, _text_column_width-1).decode().strip()
                if len(text2) > 0:
                    text1 = _stdscr.instr(y, 0, _first_column_width).decode().strip()

                    ## Split the text at the first occurrence of space because of Number in it
                    #parts = text1.split(' ', 1)
                    # Split the text at the third occurrence of space because of Number in it
                    parts = text1.split(' ', 3)
                    # Use part after the first space if it exists, otherwise return an empty string
                    if len(parts) > 3:
                        text1 = parts[3]

                    _safe_print_curses_internal(text1, item_to_find, media_index, force_new_line_if_not_empty = True)
                    # call itself again to print info on the new line, 
                    # but with force_new_line=FALSE
                    _safe_print_curses_update_status_internal(item_to_find, text, status, status_color, metrics_tuple, media_index, False)
                    return

        if False: #if _debug #for checking adjustment
            if x >= width: 
                return
            text = f"[i{media_index}s{item_to_find[0]}p{item_to_find[1]}t{item_to_find[2]}]"
            _stdscr.addstr(y, x, text[:width-x-1])
            _stdscr.refresh()
            return

        dim = curses.A_DIM if check_for_dimming(item_to_find) else 0

        isfirst = True
        for text, color in metrics_tuple:
            if x >= width: 
                break
            if not isfirst:
                if x < width: 
                    _stdscr.addstr(y, x, "/"[:width-x-1], curses.color_pair(0) | dim)
                x += 1
            if color is not None:
                if x < width: 
                    _stdscr.addstr(y, x, text[:width-x-1], curses.color_pair(color.value) | dim) 
            else:
                if x < width: 
                    _stdscr.addstr(y, x, text[:width-x-1], curses.color_pair(0) | dim) 
            x += len(text)          
            isfirst = False
        
        # Ensuring the text fits in the width
        x += 1
        tw_max = min(width-x-1, _text_column_width-18)
        if status_color:
            if x < width: 
                _stdscr.addstr(y, x, status[:tw_max], curses.color_pair(status_color.value) | dim) 
        else:
            if x < width: 
                _stdscr.addstr(y, x, status[:tw_max], curses.color_pair(0) | dim) 
        _stdscr.refresh()

    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)
 
    

def init_display(master_playlist: M3U8, limit_downloads: int):
    global _stdscr
    global _number_of_data_columns

    print(f"\nSTART: {master_playlist.Type}, {master_playlist.Name}, {master_playlist.URI}")
    print(master_playlist.FileDownloaded.Response_body.decode('utf-8'))

    _number_of_data_columns = len(master_playlist.Media_Streams)

    for i, stream in enumerate(master_playlist.Media_Streams):
        print(f'Stream {i + 1}: ' +  str(stream))

    for i, stream in enumerate(master_playlist.Media_Audios):
        print(f'Audio {i + 1}: ' +  str(stream))

    if _debug:
        _stdscr = None
        return

    #curses._CursesWindow
    _stdscr = curses.initscr() 

    #How to use terminal color palette with curses
    #https://stackoverflow.com/questions/18551558/how-to-use-terminal-color-palette-with-curses
    curses.start_color()
    curses.use_default_colors()
    for i in range(0, curses.COLORS):
        curses.init_pair(i, i, -1)

    _stdscr.scrollok(True)
    _stdscr.idlok(True)

    # Get the screen dimensions
    height, width = _stdscr.getmaxyx() 
    _stdscr.addstr(0, 0, f"Num of streams = {len(master_playlist.Media_Streams)}, Limit = {limit_downloads}")  
    for i, stream in enumerate(master_playlist.Media_Streams):
        parsed_url = urlparse(stream.URI)                            
        filename = os.path.basename(parsed_url.path)

        text = f"{filename} {stream.Resolution}"

        x = _first_column_width + i * _text_column_width + int(_text_column_width/2.0 - len(text)/2.0) #48 27,  (4) is for counter
        if x < width:
            _stdscr.addstr(0, x, text[:width-x-1])
    _stdscr.refresh()

        #print(f'Stream {i + 1}: ' +  str(stream))

    #for i, stream in enumerate(master_playlist.Media_Audios):
    #    print(f'Audio {i + 1}: ' +  str(stream))

    _stdscr.nodelay(True)
  

def find_or_nearest_tuple(lst, target):
    # scan the list descending: from bottom to top
    # -2 = didn't find it at all
    # -1 = did not find the specified element, but an older one has already been found
    # 0+ = element is found, exact position in the list is returned

    target_segment, target_part, target_filetype = target
    #nearest_tuple = None
    #smallest_diff = float('inf')  # Initialize with infinity

    for i in range (len(lst) - 1, -1, -1):
        item = lst[i]

        if (item[0] == 0 and item[1] == 0):
            if (target_segment == 0 and target_part == 0):
                if item[2] == target_filetype:
                    return i
                else:
                    continue
            else:
                continue

        if item[0] == target_segment and item[1] == target_part and item[2] == target_filetype:
            return i
        
        #how much to check old segments affects the likelihood of a long response
        rotten_segment = 3
        if ((item[0] < target_segment-rotten_segment) or (item[0] == target_segment-rotten_segment and item[1] < target_part)) and (item[2] == target_filetype):
            return -1
    
    #for part1, part2 in lst:
    #    if (part1, part2) == (target1, target2):
    #        return (part1, part2)
    #    
    #    if part1 >= target1 and part2 >= target2:
    #        diff = (part1 - target1) + (part2 - target2)
    #        if diff < smallest_diff:
    #            smallest_diff = diff
    #            nearest_tuple = (part1, part2)

    #didn't find it at all
    return -2

def display_getch(wait_for_key: bool = False) -> int:
    global _stdscr

    if _debug:
        return
    
    if not _stdscr:
        return

    _stdscr.nodelay(not wait_for_key)

    # Wait for user input to exit    
    return _stdscr.getch()

def display_finish():
    global _stdscr

    if _debug:
        return
    
    if not _stdscr:
        return

    # Get the screen dimensions
    height, width = _stdscr.getmaxyx()    
    for i in range(height):
        text1 = _stdscr.instr(i, 0, curses.COLS).decode().strip()
        if len(text1) > 0:
            _display_buffer_lines.append(text1)

    # Explicitly reset terminal settings
    curses.nocbreak()
    _stdscr.keypad(False)
    curses.echo()
    curses.endwin()
    _stdscr = None
    #print("curses.endwin()")

    #write all the buffer to the screen
    for l in _display_buffer_lines:
        print(l)
    _display_buffer_lines.clear()


def display_downloadstatus(type: m3u8.TypeDownload, segmentnum: int, partnum: int, status: str, status_color: Colors, metrics_tuple: tuple, download_metrics: DownloadMetrics, media_index: int = None):
    global _processed_parts

#    _current_ipart = i_part
#    _current_part = (last_part.Segment, last_part.PartNum)
#                        s = i_part_to_download // max_parts_in_segment
#                        p = i_part_to_download % max_parts_in_segment
#                            part_to_download = playlist0.Media_Parts[len(playlist0.Media_Parts) - (i_part - i_part_to_download) - 1]
#                            processed_parts.append(i_part_to_download)
#   
    text = ""
    if metrics_tuple is None and download_metrics is not None:
        #Response_time – ms
        #Download_time – ms
        #Download_speed – bits per second
        text = f"{(download_metrics.Download_time):5.1f}/{download_metrics.Response_time:4.0f}/{download_metrics.Download_speed/1000/1000:5.1f}"
    
    if status is None:
        status = download_metrics.Status

    if media_index is None:
        media_index = -1

    _safe_print_curses_update_status((segmentnum, partnum, type), text, status, status_color, metrics_tuple, media_index)
    
def format_string_15(input_str: str, max: int = 23):
    try:
        # Ensure the string is at most 15 characters
        if len(input_str) > max:
            return input_str[:max]
        else:
            # Pad with spaces if the string is less than 15 characters
            return input_str.ljust(max)
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)

def display_downloadstarted(type: m3u8.TypeDownload, segmentnum: int, partnum: int, url_to_download: str, media_index: int, force_new_line: bool = False):
    if _debug:
        return
    
    try:
        parsed_url = urlparse(url_to_download)                            
        query = "?" + parsed_url.query if parsed_url.query else ""    
        filename = os.path.basename(parsed_url.path)
        #fileextension = filename.rsplit('.', maxsplit=1)[1]
        #filename = f"{fileextension} part={partnum}"
        fileextension = filename[-15:]

        if type == m3u8.TypeDownload.FILE_PART:
            if segmentnum > 0:
                filename = f"{fileextension} part={partnum}"
            else:
                filename = fileextension
        elif type == m3u8.TypeDownload.MANIFEST_MEDIA:
            #filename += f"media_N.m3u8 part={partnum}"
            if segmentnum > 0:
                filename = f"{fileextension} part={partnum}"
            else:
                filename = fileextension

        text = f"{format_string_15(filename)}"

        #text = f"Dload: {segmentnum}-{partnum} {filename + query}"
        #last_line = 
        _safe_print_curses(text, (segmentnum, partnum, type), media_index, force_new_line)


        #_safe_print(f"Dload: {segmentnum}-{partnum} {filename + query}")
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)

def display_message(message: str):
    _safe_print(f"Info:  {message}")

def display_error(message: str):
    _safe_print(f"ERROR: {message}")


def calc_stat_values(float_values: List[float]):
    # Calculate minimum, average, and maximum
    min_value = min(float_values)
    max_value = max(float_values)
    average_value = statistics.mean(float_values)

    # Calculate percentiles using numpy
    p50_value = np.percentile(float_values, 50)
    p75_value = np.percentile(float_values, 75)
    p95_value = np.percentile(float_values, 95)
    p99_value = np.percentile(float_values, 99)

    return (min_value, average_value, max_value, p50_value, p75_value, p95_value, p99_value)

def color_stat_value(value: float, limit: float, reverse: bool = False) -> str:
    if (not reverse and value >= limit) or (reverse and value < limit):
        return f"\033[31m{value:7.1f}\033[0m"
    else:
        return f"{value:7.1f}"

def color_response_value(value: int, text: str, color: Colors) -> str:
    # Black: 30
    # Red: 31
    # Green: 32
    # Yellow: 33
    # Blue: 34
    # Magenta: 35
    # Cyan: 36
    # White: 37
    text = f"{text}: {value}"
    if value > 0:
        c = 30 + color.value
        # match color:
        #     case Colors.BLACK: c = 30
        #     case Colors.RED: c = 31
        #     case Colors.GREEN: c = 32
        #     case Colors.YELLOW: c = 33
        #     case Colors.BLUE: c = 34
        #     case Colors.MAGENTA: c = 35
        #     case Colors.CYAN: c = 36
        #     case Colors.WHITE: c = 37
        return f"\033[{c}m{text}\033[0m"
    else:
        return text


def display_summary_substat_nocurses(section_name: str, responses: List[int], stat: List[tuple[float, float, float]], bandwidth_limit: float, part_duration_limit: float):
    print(f"{section_name}\t", end="")
    if responses is None:
        print("NO DATA")
        return
    #delay_value = for [tup[0] for tup in stat]
    delay_value = sum(tup[0] for tup in stat if tup[0] > part_duration_limit * 1000)

    print(f"total: {responses[0]+responses[1]+responses[2]+responses[3]}\t| sum_delay={delay_value/1000:.1f}s") #sum(responses)

    print(f"\tok   : {responses[0]}\t|\t\t\t    min     avg     max     p50     p75     p95     p99")

    t = calc_stat_values([tup[0] for tup in stat])
    print(f"\t{color_response_value(responses[1], "stale", Colors.MAGENTA)}\t| response_time (ms):\t", end="") #MAGENTA
    for s in t:
        print(color_stat_value(s, part_duration_limit * 1000), end=" ")
    print()

    t = calc_stat_values([tup[1] for tup in stat])
    print(f"\t{color_response_value(responses[2], "delay", Colors.YELLOW)}\t| download_time (ms):\t", end="") #YELLOW
    for s in t:
        print(color_stat_value(s, 150), end=" ")
    print()    

    t = calc_stat_values([tup[2]/1000/1000 for tup in stat])
    print(f"\t{color_response_value(responses[3], "error", Colors.RED)}\t| download_speed(Mbps):\t", end="") #RED
    for s in t:
        print(color_stat_value(s, bandwidth_limit, reverse=True), end=" ")
    print()    
    print()

    # print(f"total: {responses[0]+responses[1]+responses[2]}\t\t\t\t    min     avg     max     p50     p75     p95     p99")

    # t = calc_stat_values([tup[0] for tup in stat])
    # print(f"\tok: {responses[0]}\t\t|response_time (ms):\t"{t[0]:7.1f} {t[1]:7.1f} {t[2]:7.1f} {t[3]:7.1f} {t[4]:7.1f} {t[5]:7.1f} {t[6]:7.1f}")

    # t = calc_stat_values([tup[1] for tup in stat])
    # print(f"\twarnings: {responses[1]}\t|download_time (ms):\t{t[0]:7.1f} {t[1]:7.1f} {t[2]:7.1f} {t[3]:7.1f} {t[4]:7.1f} {t[5]:7.1f} {t[6]:7.1f}")

    # t = calc_stat_values([tup[2]/1000/1000 for tup in stat])
    # print(f"\terrors: {responses[2]}\t|download_speed (Mbps):\t{t[0]:7.1f} {t[1]:7.1f} {t[2]:7.1f} {t[3]:7.1f} {t[4]:7.1f} {t[5]:7.1f} {t[6]:7.1f}")
    # print()



    # print(f"total: {responses[0]+responses[1]+responses[2]}")

    # t = calc_stat_values([tup[0] for tup in stat])
    # print(f"\tok: {responses[0]}\t\tresponse_time (ms):\tmin={t[0]:.0f}, avg={t[1]:.0f}, max={t[2]:.0f}, p50={t[3]:.0f}, p75={t[4]:.0f}, p95={t[5]:.0f}, p99={t[6]:.0f}")

    # t = calc_stat_values([tup[1] for tup in stat])
    # print(f"\twarnings: {responses[1]}\tdownload_time (ms):\tmin={t[0]:7.1f}, avg={t[1]:7.1f}, max={t[2]:7.1f}, p50={t[3]:7.1f}, p75={t[4]:7.1f}, p95={t[5]:7.1f}, p99={t[6]:7.1f}")

    # t = calc_stat_values([tup[2]/1000/1000 for tup in stat])
    # print(f"\terrors: {responses[2]}\tdownload_speed (Mbps):\tmin={t[0]:7.1f}, avg={t[1]:7.1f}, max={t[2]:7.1f}, p50={t[3]:7.1f}, p75={t[4]:7.1f}, p95={t[5]:7.1f}, p99={t[6]:7.1f}")
    # print()

def display_summary_nocurses(master_playlist: M3U8, summary_response_manifests: Dict[int, List[int]], summary_stat_manifests: Dict[int, List[tuple[float, float, float]]], summary_response_parts: Dict[int, List[int]], summary_stat_parts: Dict[int, List[tuple[float, float, float]]], summary_manifest_part_durations: Dict[int, float] ) :
    print(f"\nSUMMARY: {master_playlist.URI}\n")

    media_index = 0
    for media in master_playlist.Media_Streams:
        parsed_url = urlparse(media.URI)                            
        filename = os.path.basename(parsed_url.path)        

        bandwidth = 0
        try:
            bandwidth = int(media.Bandwidth)
        except Exception as e:
            pass

        part_duration = summary_manifest_part_durations.get(media_index)
        if part_duration is None:
            part_duration = 0.0

        print(f"MEDIA #{media_index+1}: {filename}, {media.Resolution}, {bandwidth/1000/1000:.1f} Mbps ({media.Bandwidth}), Part={part_duration:.3f} sec")
        display_summary_substat_nocurses("  M3U8", summary_response_manifests.get(media_index), summary_stat_manifests.get(media_index), bandwidth/1000.0/1000.0, part_duration)
        display_summary_substat_nocurses("  PARTS", summary_response_parts.get(media_index), summary_stat_parts.get(media_index), bandwidth/1000.0/1000.0, part_duration)
        print()

        media_index += 1
