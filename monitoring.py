import datetime
from enum import Enum
import os
import sys
import threading
import time
import traceback
from typing import Dict, List
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import display
import logs
import m3u8
import concurrent.futures

# A lock object to ensure thread-safe printing
_global_fileslog_lock = threading.Lock()
_list_of_logged_files = {}
_logged_files_id = 0

_global_summaryparts_lock = threading.Lock()
_summary_response_parts: Dict[int, List[int]] = {}
_summary_stat_parts: Dict[int, List[tuple[float, float, float]] ] = {}
_summary_response_manifests: Dict[int, List[int]] = {}
_summary_stat_manifests: Dict[int, List[tuple[float, float, float]] ] = {}
_summary_manifest_part_duration: Dict[int, float] = {}

_global_escape_pressed = False

class SummaryStatus(Enum):
    OK = 0
    STALE = 1
    DELAY = 2
    ERROR = 3
    
    def __str__(self):
        return '%s' % self.value


class ThreadPoolExecutorStackTraced(concurrent.futures.ThreadPoolExecutor):
    def submit(self, fn, *args, **kwargs):
        """Submits the wrapped function instead of `fn`"""

        return super(ThreadPoolExecutorStackTraced, self).submit(
            self._function_wrapper, fn, *args, **kwargs)

    def _function_wrapper(self, fn, *args, **kwargs):
        """Wraps `fn` in order to preserve the traceback of any kind of
        raised exception

        """
        try:
            return fn(*args, **kwargs)
        except Exception:
            raise sys.exc_info()[0](traceback.format_exc())  # Creates an
                                                             # exception of the
                                                             # same type with the
                                                             # traceback as
                                                             # message


def remove_query_params(url, extra_params: List[str]):
    # Parse the URL into components
    parsed_url = urlparse(url)
    
    # Parse the existing query parameters
    query_params = parse_qs(parsed_url.query)
    
    # Update/add the parameters
    for key in extra_params:
        query_params.pop(key, None)
    
    # Encode back the query parameters
    new_query_string = urlencode(query_params, doseq=True)
    
    # Reconstruct the URL with updated query parameters
    new_url = urlunparse(
        (
            parsed_url.scheme or "",
            parsed_url.netloc or "",
            parsed_url.path or "",
            parsed_url.params or "",
            new_query_string,
            parsed_url.fragment or "",
        )
    )
    return new_url

def add_or_update_query_params(url, extra_params):
    # Parse the URL into components
    parsed_url = urlparse(url)
    
    # Parse the existing query parameters
    query_params = parse_qs(parsed_url.query)
    
    # Update/add the parameters
    for key, value in extra_params.items():
        query_params[key] = [value]
    
    # Encode back the query parameters
    new_query_string = urlencode(query_params, doseq=True)
    
    # Reconstruct the URL with updated query parameters
    new_url = urlunparse(
        (
            parsed_url.scheme or "",
            parsed_url.netloc or "",
            parsed_url.path or "",
            parsed_url.params or "",
            new_query_string,
            parsed_url.fragment or "",
        )
    )
    return new_url

def add_suffix_to_filename(filepath, suffix):
    # Split the path into directory, base filename, and extension
    directory, filename = os.path.split(filepath)
    base, ext = os.path.splitext(filename)

    # Create the new filename with the suffix
    new_filename = f"{base}{suffix}{ext}"

    # Join the directory and the new filename
    new_filepath = os.path.join(directory, new_filename)
    
    return new_filepath

def _safe_add_summaryparts_to_list(*args, **kwargs):
    with _global_summaryparts_lock:
        return _safe_add_summaryparts_to_list_internal(*args, **kwargs)

# Function to add a new object to the dictionary
def _safe_add_summaryparts_to_list_internal(media_index: int, summary: SummaryStatus, metrics: m3u8.DownloadMetrics):
    global _summary_response_parts
    global _summary_stat_parts

    if _summary_response_parts.get(media_index) is None:
        v = [0,0,0,0]
        v[summary.value] = 1
        _summary_response_parts[media_index] = v
    else:
        v = _summary_response_parts[media_index]
        v[summary.value] += 1
        _summary_response_parts[media_index] = v

    if _summary_stat_parts.get(media_index) is None:
        v = [tuple((metrics.Response_time, metrics.Download_time, metrics.Download_speed))]
        _summary_stat_parts[media_index] = v
    else:
        v = _summary_stat_parts[media_index]
        v.append(tuple((metrics.Response_time, metrics.Download_time, metrics.Download_speed)))

    pass

def _safe_add_summarymanifests_to_list(*args, **kwargs):
    with _global_summaryparts_lock:
        return _safe_add_summarymanifests_to_list_internal(*args, **kwargs)

# Function to add a new object to the dictionary
def _safe_add_summarymanifests_to_list_internal(media_index: int, summary_response, summary_stat, summary_manifest_part_duration: float):
    global _summary_response_manifests
    global _summary_stat_manifests
    global _summary_manifest_part_duration

    _summary_response_manifests[media_index] = summary_response
    _summary_stat_manifests[media_index] = summary_stat
    _summary_manifest_part_duration[media_index] = summary_manifest_part_duration

    pass  


def run_task_for_downloading_part_1(segmentnum: int, partnum: int, url_to_download: str, media_manifest: m3u8.MediaStream, manifest: m3u8.M3U8, path_to_save: str = None, media_index: int = None, file_id: int = None) -> bool:
    try:
        #HTTP1
        metrics = m3u8.download_file_http1(url_to_download, path_to_save)   #-> wait for response in parallel, and print result on screen
        #HTTP2
        #metrics = m3u8.download_file_http2(url_to_download, path_to_save)   #-> wait for response in parallel, and print result on screen
        #display.display_downloadstatus(m3u8.TypeDownload.FILE_PART, segmentnum, partnum, metrics)
        ssummary = display_status_of_download(m3u8.TypeDownload.FILE_PART, segmentnum, partnum, metrics, media_manifest, manifest, media_index, file_id)
        _safe_add_summaryparts_to_list(media_index, ssummary, metrics)
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)


def _safe_add_filetolog_to_dict(*args, **kwargs) -> int:
    with _global_fileslog_lock:
        return _safe_add_filetolog_to_dict_internal(*args, **kwargs)

# Function to add a new object to the dictionary
def _safe_add_filetolog_to_dict_internal(data) -> int:
    global _logged_files_id

    _logged_files_id += 1

    id = _logged_files_id
    _list_of_logged_files[id] = data
    return id

def _safe_get_filetolog_from_dict(*args, **kwargs) -> int:
    with _global_fileslog_lock:
        return _safe_get_filetolog_from_dict_internal(*args, **kwargs)

# Function to add a new object to the dictionary
def _safe_get_filetolog_from_dict_internal(file_id) -> any:
    obj = _list_of_logged_files.pop(file_id, None)
    if obj is not None:
        return obj
    else:
        return None


def display_download_started(type: m3u8.TypeDownload, url: str, segment: int, part: int, media_index: int, initiator: str, force_new_line: bool = False) -> int:
    fileid = _safe_add_filetolog_to_dict((
        datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],
        type, 
        url, 
        segment, 
        part, 
        media_index,
        threading.current_thread().name,
        initiator
        ))
    display.display_downloadstarted(type, segment, part, url, media_index, force_new_line)
    return fileid

def display_status_of_download(type: m3u8.TypeDownload, segmentnum: int, partnum: int, metrics: m3u8.DownloadMetrics = None, media_manifest: m3u8.MediaStream = None, manifest: m3u8.M3U8 = None, media_index:int = None, file_id: int = None) -> SummaryStatus:    
    summary_status: SummaryStatus = SummaryStatus.OK
    
    try:
        if metrics is None:
            if manifest is not None:
                metrics = manifest.FileDownloaded
            else:
                display.display_downloadstatus(type, segmentnum, partnum, "NO DATA", display.Colors.RED, [(" - ", display.Colors.RED),(" - ", display.Colors.RED),(" - ", display.Colors.RED)], None, media_index)
                return SummaryStatus.ERROR

        if metrics.Response_time is None:
            metrics.Response_time = 0
        if metrics.Download_time is None:
            metrics.Download_time = 0
        if metrics.Download_speed is None:
            metrics.Download_speed = 0

        status: str = metrics.Status
        status_color: display.Colors = None
        download_time_color: display.Colors = None
        response_time_color: display.Colors = None
        download_speed_color: display.Colors = None

        if metrics.HTTP_code != 200:
            #status = f'ERROR {metrics.HTTP_code} {status}'
            status = f'ERROR {metrics.HTTP_code}'
            status_color = display.Colors.RED 
            summary_status = SummaryStatus.ERROR

            if metrics.Response_time or metrics.Response_time == 0:
                response_time_color = display.Colors.RED
            if metrics.Download_time is None or metrics.Download_time == 0:
                download_time_color = display.Colors.RED
            # if metrics.Download_speed is below in the main part

        elif type == m3u8.TypeDownload.MANIFEST_MEDIA:
            if manifest is None:
                return SummaryStatus.ERROR

            lastpart: m3u8.MediaPart = None
            if len(manifest.Media_Parts) > 0:
                lastpart = manifest.Media_Parts[len(manifest.Media_Parts)-1]
                
            # Detect part to be downloaded and to download it
            max_parts_in_segment = 0
            if manifest.EXT_X_PartInf_Part_Target > 0:
                max_parts_in_segment = int(manifest.EXT_X_Target_Duration // round(manifest.EXT_X_PartInf_Part_Target, 1))
            
            if not lastpart:
                status = f'No Parts'
                status_color = display.Colors.RED 
                summary_status = SummaryStatus.ERROR
            elif (partnum >= max_parts_in_segment):
                status = f'ERROR OR={partnum} (XTD={manifest.EXT_X_Target_Duration} // XPT={round(manifest.EXT_X_PartInf_Part_Target, 1)})' #OR= Out of range ?p=X
                status_color = display.Colors.RED 
                summary_status = SummaryStatus.ERROR
            elif (lastpart.Segment < segmentnum) or (lastpart.Segment == segmentnum and lastpart.PartNum < partnum):
                status = f'STALE {lastpart.Segment}-{lastpart.PartNum}'
                status_color = display.Colors.MAGENTA
                summary_status = SummaryStatus.STALE
            
            if ((manifest.EXT_X_PartInf_Part_Target > 0 and metrics.Response_time > manifest.EXT_X_PartInf_Part_Target * 1000)
                    or (metrics.Response_time > 500)):  #Response_time in ms, but PartTarget in sec
                status = status + " DELAY" if len(status)>0 else "DELAY"
                response_time_color = display.Colors.CYAN
                #summary_status = SummaryStatus.DELAY
            if (manifest.EXT_X_Target_Duration > 0 and metrics.Response_time > manifest.EXT_X_Target_Duration * 1000):  #Response_time in ms, but TargetDuration in sec
                status = status + " DELAY" if len(status)>0 else "DELAY"
                response_time_color = display.Colors.YELLOW
                summary_status = SummaryStatus.DELAY

            if lastpart is not None and ((lastpart.Segment > segmentnum) or (lastpart.Segment == segmentnum and lastpart.PartNum > partnum)):
                status += f' {lastpart.Segment}-{lastpart.PartNum}'
                if status_color == display.Colors.WHITE:
                    status_color = display.Colors.CYAN

            #Download_time in ms
            #Download_speed in bps = bits per second
            if (media_manifest is not None and metrics.Download_speed < media_manifest.Bandwidth) and (status_color != display.Colors.RED): 
                status += " SLOW"
                download_speed_color = display.Colors.CYAN

        elif type == m3u8.TypeDownload.FILE_PART:
            if metrics.Response_time > manifest.EXT_X_PartInf_Part_Target * 1000:  #Response_time in ms, but PartTarget in sec
                status = "DELAY"
                response_time_color = display.Colors.YELLOW
                summary_status = SummaryStatus.DELAY
            
            #Download_time in ms
            #Download_speed in bps = bits per second
            if metrics.Download_time > 150 or (media_manifest is not None and metrics.Download_speed < media_manifest.Bandwidth):
                status += " SLOW"
                if metrics.Download_time > 150:
                    download_time_color = display.Colors.YELLOW
                else:
                    download_speed_color = display.Colors.CYAN

        if metrics.Download_speed is None or metrics.Download_speed == 0.0:
            download_speed_color = display.Colors.RED

        #metrics_str = f"{(metrics.Download_time):5.1f}/{metrics.Response_time:4.0f}/{metrics.Download_speed/1000/1000:5.1f}"

        metrics_tuple = [
            (f"{metrics.Response_time:4.0f}", response_time_color),
            (f"{metrics.Download_time:5.1f}", download_time_color),
            (f"{metrics.Download_speed/1000/1000:5.1f}", download_speed_color)
        ]    

        #if status_color is None and (download_time_color is not None or response_time_color is not None or download_speed_color is not None):
        status_color = min([status_color, download_time_color, response_time_color, download_speed_color], key=lambda x: x.value if x is not None else 1000)

        #write to log
        if file_id is not None:
            obj = _safe_get_filetolog_from_dict(file_id)
            if obj is not None:
                object_to_print = (obj + (
                                        status,
                                        status_color,
                                        metrics.HTTP_code,
                                        metrics.Status,
                                        f"{metrics.Time_headers:.1f}" if metrics and metrics.Time_headers is not None else "0",
                                        f"{metrics.Download_time:.1f}" if metrics and metrics.Download_time is not None else "0",
                                        f"{metrics.Response_time:.0f}" if metrics and metrics.Response_time is not None else "0",
                                        f"{metrics.Download_speed/1000/1000:.1f}" if metrics and metrics.Download_speed is not None else "0"                                        
                                    )
                                    + (tuple([tup[1] for tup in metrics.Headers]) if metrics.Headers is not None else ()))
                
                if metrics.HTTP_code != 200 or (status_color is not None and status_color == display.Colors.RED):
                    logs.write_error(object_to_print)
                    pass
                elif status_color is not None:
                    logs.write_warning(object_to_print)
                    pass
                else:
                    logs.write_info(object_to_print)
                    pass
                
        display.display_downloadstatus(type, segmentnum, partnum, status, status_color, metrics_tuple, metrics, media_index)

        return summary_status
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)
        return SummaryStatus.ERROR
    
    
def run_tasks_for_media_manifest_1(media_manifest: m3u8.M3U8, media_index: int, limit_downloads: int) -> bool:
    global _global_escape_pressed

    current_ipart: int = 0
    current_part = (0,0)
    processed_parts : List[int] = []
    task_id = 0
    num_of_errors_in_a_raw = 0

    summary_response_manifests: List[int] = [0,0,0,0]
    summary_stat_manifests: List[tuple[float, float, float]] = []
    summary_manifest_part_duration = 0.0

    # init as first playlist to download
    url_llhls_playlist = media_manifest.URI

    path_to_save_files: str = None
    #path_to_save_files = "/Users/apih/Temp/1/" # must ends with /

    timer_start_ms: float = time.time()

    try:
        #ThreadPoolExecutorStackTraced
        #with concurrent.futures.ThreadPoolExecutor(thread_name_prefix=f"Media{media_index}PartDownload") as media_executor:        
        with ThreadPoolExecutorStackTraced(thread_name_prefix=f"Media{media_index}PartDownload") as media_executor:
            while task_id <= limit_downloads and (not _global_escape_pressed): # True: #10
                # if Esq key is pressed, then finilase the thread
                keypressed = display.display_getch(False)
                if keypressed == 27:  
                    _global_escape_pressed = True 
                    break   
                
                task_id += 1
                timer_start_ms = time.time()
                
                filepath: str = None

                # Load manifest:
                # – for the first time without LL query stribng
                # – for later with LL query string attributes
                parsed_url = urlparse(url_llhls_playlist)                        
                query_params = parse_qs(parsed_url.query)
                
                s = "0"
                p = "0"
                force_new_line_on_screen = False
                qp = query_params.get("_HLS_msn") if query_params else None
                if isinstance(qp, list):
                    s = qp[0]
                qp = query_params.get("_HLS_part") if query_params else None
                if isinstance(qp, list):
                    p = qp[0]
                if num_of_errors_in_a_raw >= 3:
                    if qp is not None:
                        url_llhls_playlist = remove_query_params(url_llhls_playlist, ['_HLS_msn', '_HLS_part'])  
                        force_new_line_on_screen = True
                        if num_of_errors_in_a_raw > 5:
                            time.sleep(1)  # Sleep for 1 second

                if path_to_save_files:
                    filename = add_suffix_to_filename(os.path.basename(parsed_url.path), f"-{s}_{p}")
                    filepath = path_to_save_files + filename
                
                file_id = display_download_started(m3u8.TypeDownload.MANIFEST_MEDIA, url_llhls_playlist, int(s), int(p), media_index, media_manifest.URI, force_new_line_on_screen)
                playlist0 = m3u8.load_and_parse_manifest(url_llhls_playlist, filepath)
                #display.display_downloadstatus(m3u8.TypeDownload.MANIFEST_MEDIA, int(s), int(p), manifest=playlist0)
                ssummary = display_status_of_download(m3u8.TypeDownload.MANIFEST_MEDIA, int(s), int(p), None, media_manifest, playlist0, media_index, file_id)
                summary_response_manifests[ssummary.value] += 1
                summary_stat_manifests.append((playlist0.FileDownloaded.Response_time, playlist0.FileDownloaded.Download_time, playlist0.FileDownloaded.Download_speed))
                summary_manifest_part_duration = playlist0.EXT_X_PartInf_Part_Target

                # Load "init_mp4" file if need
                if path_to_save_files:
                    parsed_url = urlparse(playlist0.EXT_X_Map_URI)                        
                    filename = add_suffix_to_filename(os.path.basename(parsed_url.path), f"_init")
                    filepath = path_to_save_files + filename
                    if not os.path.exists(filepath):
                        display.display_downloadstarted(m3u8.TypeDownload.FILE_INIT, 0, 0, playlist0.EXT_X_Map_URI, media_index)
                        m3u8.download_file_http1(playlist0.EXT_X_Map_URI, filepath)   #-> wait for response in parallel, and print result on screen

                # check for 400, 500, etc errors of getting manifests
                # validate that CAN-BLOCK is YES

                if playlist0.FileDownloaded.HTTP_code != 200 or playlist0.Type != m3u8.TypeM3U8.VIDEO:
                    num_of_errors_in_a_raw += 1
                    continue
                else:
                    num_of_errors_in_a_raw = 0

                # Detect part to be downloaded and download it
                max_parts_in_segment = 0
                if playlist0.EXT_X_PartInf_Part_Target > 0:
                    max_parts_in_segment = int(playlist0.EXT_X_Target_Duration // round(playlist0.EXT_X_PartInf_Part_Target, 1))
                if len(playlist0.Media_Parts) > 0:
                    last_part = playlist0.Media_Parts[len(playlist0.Media_Parts) - 1]

                    #playlist0.EXT_X_Target_Duration
                    #playlist0.EXT_X_PartInf_Part_Target

                    i_part = int(last_part.Segment * (max_parts_in_segment)) + last_part.PartNum
                    
                    # if no new part is inside the manifest
                    if current_ipart > 0 and i_part <= current_ipart:
                        # no new parts in new manifest, then it's a problem
                        # notify user on the screen        
                        
                        #!display.display_error(f"Manifest {playlist0.URI} does not contain new parts compared to the previous one! Last knows part was: {current_part[0]}/{current_part[1]} ")
                        pass
                    else:
                        if i_part > current_ipart + 3:
                            # if more than 3 parts are skipped then it's a problem
                            # need just to skip all of those part and to download just the latest one 

                            #Count how many lines are skipped
                            # write ... instead of part number
                            # and continue from the latest part
                            current_ipart = i_part - 1

                        # if 1-2 parts are skipped, then need to download them as well, because it can be CDN delivery issue
                        # ??? but to download in reverse sequence – the latestes must be downloaded first
                        for i_part_to_download in range(current_ipart+1, i_part+1):

                            s = i_part_to_download // max_parts_in_segment
                            p = i_part_to_download % max_parts_in_segment

                            if i_part_to_download not in processed_parts:
                                part_to_download = playlist0.Media_Parts[len(playlist0.Media_Parts) - (i_part - i_part_to_download) - 1]
                                processed_parts.append(i_part_to_download)

                                filepath = None
                                if path_to_save_files:
                                    parsed_url = urlparse(part_to_download.URI)                        
                                    filename = add_suffix_to_filename(os.path.basename(parsed_url.path), f"_{s}_{p}")
                                    filepath = path_to_save_files + filename
                                
                                
                                file_id = display_download_started(m3u8.TypeDownload.FILE_PART, part_to_download.URI, int(s), int(p), media_index, playlist0.URI)
                                future = media_executor.submit(run_task_for_downloading_part_1, s, p, part_to_download.URI, media_manifest, playlist0, filepath, media_index, file_id)
                                #future.add_done_callback(long_task_callback_1)
                                #m3u8.download_file(part_to_download.URI, filepath)   #-> wait for response in parallel, and print result on screen
                        
                    current_ipart = i_part
                    current_part = (last_part.Segment, last_part.PartNum)

                    next_part = 0
                    next_msn = 0
                    if last_part.Final:
                        next_msn = last_part.Segment + 1 
                        next_part = 0
                    else:
                        next_msn = last_part.Segment
                        next_part = last_part.PartNum + 1

                    #need to validate that sum of parts is equal to part_target_duration

                    # media_3.m3u8?_HLS_msn=7&_HLS_part=3
                    url_llhls_playlist = add_or_update_query_params(playlist0.URI, {'_HLS_msn': next_msn, '_HLS_part': next_part})  

                    if next_part >= max_parts_in_segment: #== 6:
                        #!display.display_error(f"Illegal request for part #{next_part} was generated outside the allowed range 0-{max_parts_in_segment-1}, URL = {url_llhls_playlist}")
                        pass

                    # server will block the request till exact requested part msn+part is really prepared and be ready for downloading from server
                    #set a task to download next manifest
                    #m3u8.load_manifest(url_llhls_playlist) # -> this will have huge waiting response time, but after it must be downloaded fastly

                else:
                    # no parts at all in new manifest, then it's a problem
                    
                    # notify user on the screen        
                    #display.display_error(f"Manifest {playlist0.URI} does not contain parts at all! Last knows part was: {current_part[0]}/{current_part[1]} ")                        
                    #pass

                    # Sleep for at least 1 second or EXT_X_Target_Duration
                    if playlist0.EXT_X_Target_Duration > 0:
                        exec_time_s = time.time() - timer_start_ms
                        time_to_sleep = float(playlist0.EXT_X_Target_Duration) - exec_time_s
                        if time_to_sleep > 0:
                            time.sleep(time_to_sleep)
                    else:
                        time.sleep(1) 
                            
        _safe_add_summarymanifests_to_list(media_index, summary_response_manifests, summary_stat_manifests, summary_manifest_part_duration)
        
        # write "STREAM #N IS DONE"
        #display_finish_of_download(media_index, task_id)
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)

def print_result_from_media_1():
    pass

def coordinator(master_playlist: m3u8.M3U8, limit_downloads: int = 10):
    global _summary_response_parts
    global _summary_stat_parts
    global _summary_response_manifests
    global _summary_stat_manifests

    # must call functions async 
    # wait for result and print information on a screen

    #for i, stream in enumerate(master_playlist.Media_Streams):
    if len(master_playlist.Media_Streams) == 0:
        return

    #media_list = []
    #media_list.append(master_playlist.Media_Streams[0])

    # set task to download manifest
    # wait for response
    # set task to download part 
    # set task to download maanifest for part+1

    #for each media stream run async task
    futures_media_list = []

    # media_limit:
    # -1 or 0 = all medias
    # 1..N = specified number of streams for debug
    media_limit = 0 # = 2

    #ThreadPoolExecutorStackTraced
    #with concurrent.futures.ThreadPoolExecutor(thread_name_prefix=f"Media") as master_executor: #max_workers=2
    with ThreadPoolExecutorStackTraced(thread_name_prefix=f"Media") as master_executor: #max_workers=2
        media_index = 0
        for media in master_playlist.Media_Streams:
            # Submit long running task
            future = master_executor.submit(run_tasks_for_media_manifest_1, media, media_index, limit_downloads)
            futures_media_list.append(future)
            #future.add_done_callback(long_task_callback_1)
            media_index += 1
            if media_limit > 0 and media_index >= media_limit:
                break
        #for audio in master_playlist.Media_Audios:
        #    future = master_executor.submit(run_tasks_for_media_manifest_1, audio, media_index)
        #    futures_media_list.append(future)
        #    media_index += 1
        #    if media_limit > 0 and media_index >= media_limit:
        #        break
        concurrent.futures.wait(futures_media_list)

    #exit
    if _global_escape_pressed:
        display.display_message("[Coordinator stopped by ESC] => PRESS ANY KEY")
    else:
        display.display_message("[Coordinator finished] => PRESS ANY KEY")


def display_summary(master_playlist: m3u8.M3U8):
    #prepare stat summary
    #
    # Summary:
    # - per each media stream: name, resolution, bandwidth
    # - total of files downloaded of each type
    # – for each type of file show number of oks, warnings, errors
    # – p50, p75, p95, p99 of response time, download_time, download_speed 
    display.display_summary_nocurses(master_playlist, _summary_response_manifests, _summary_stat_manifests, _summary_response_parts, _summary_stat_parts, _summary_manifest_part_duration)

