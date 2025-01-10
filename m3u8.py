import os
import random
import threading
from typing import Dict, List
import requests
import httpx
import time
import re
from urllib.parse import urljoin, urlparse
from enum import Enum

import logs

def init_client_h2() -> httpx.Client:
    return httpx.Client(http2 = True, 
                            trust_env = False, 
                            timeout = httpx.Timeout(10.0, connect=10.0, pool=60.0), 
                            limits = httpx.Limits(max_connections=500) #, max_keepalive_connections=300, keepalive_expiry=10
                            )

# global variable for HTTP2 client
_client_h2 = init_client_h2()

def beautify_number(number):
    return "{:,.0f}".format(number).replace(',', ' ')

class DownloadMetrics:
    HTTP_code: int
    Status: str
    Response_body: bytearray
    TTFB: float             #ms
    Time_headers: float     #ms
    Download_speed: float   #bps = bits per second
    Download_time: float    #ms
    Response_time: float    #ms
    Headers: List[tuple[str,str]] #tuple(str,str)

    def __init__(self, http_code: int, status: str, response_body: bytearray = None, ttfb: float = None, time_headers: float = None, download_speed: float = None, downloading_time: float = None, response_time: float = None, response_headers: List[tuple[str,str]] = None):
        self.HTTP_code = http_code
        self.Status = status
        self.Response_body = response_body
        self.TTFB = ttfb
        self.Time_headers = time_headers
        self.Download_speed = download_speed
        self.Download_time = downloading_time
        self.Response_time = response_time
        self.Headers = response_headers

    def __repr__(self):
        return (f'DownloadMetrics(http_code={self.HTTP_Code} {self.Status}'
                f'ttfb={self.TTFB:.1f} ms, '
                f'time_headers={self.Time_headers:.1f} ms, '
                f'response_time={self.Response_time:.1f} ms, '
                f'download_body_speed={self.Download_speed:.0f} bps, '
                f'download_body_time={self.Download_time:.1f} ms, '
                f'response_body_length={len(self.Response_body)} bytes, '
                f'response_headers={len(self.Headers)} items')


class MediaAudio:
    GROUP_ID: str
    URI: str

    def __init__(self, group_id: str = None, uri: str = None):
        self.GROUP_ID = group_id
        self.URI = uri

    def __str__(self):
        return (f"Media Stream Info:\n"
                f"  URI: {self.URI}\n"
                f"  GROUP_ID: {self.GROUP_ID}")
    
    def __repr__(self):
        return (f'MediaAudio(GROUP_ID={self.GROUP_ID}, '
                f'URI={self.URI}')

class MediaStream:
    Bandwidth: str
    Resolution: str
    Audio: str
    URI: str

    def __init__(self, uri: str, bandwidth: int = 0, resolution: str = None, audio: str = None):
        self.URI = uri
        self.Bandwidth = bandwidth
        self.Resolution = resolution
        self.Audio = audio

    def __repr__(self):
        return (f"MediaStream(Bandwidth='{self.Bandwidth}', "
                f"Resolution='{self.Resolution}', Audio='{self.Audio}', URI='{self.URI}')")

    def __str__(self):
        return (f"Media Stream Info:\n"
                f"  URI: {self.URI}\n"
                f"  Bandwidth: {self.Bandwidth}\n"
                f"  Resolution: {self.Resolution}\n"
                f"  Audio: {self.Audio}")

class MediaPart:
    Segment: int
    PartNum: int
    Duration: float
    URI: str
    Independent: bool
    Final: bool = False
    
    def __init__(self, segment: int, partnum: int, uri: str, duration: float, independent: bool):
        self.Segment = segment
        self.PartNum = partnum
        self.URI = uri
        self.Duration = duration
        self.Independent = independent

    def __repr__(self):
        return (
                f"MediaPart(Segment='{self.Segment}', "
                f"PartNum='{self.PartNum}', "
                f"URI='{self.URI}', "
                f"Duration={self.Duration}, "
                f"Independent={self.Independent}, "
                f"Final={self.Final})")

    def __str__(self):
        return (f"Media Part Info:\n"
                f"  Segment='{self.Segment}', "
                f"  PartNum='{self.PartNum}', "
                f"  URI: {self.URI}, \n"
                f"  Duration: {self.Duration} seconds, \n"
                f"  Independent: {self.Independent}, \n"
                f"  Final: {self.Final}")

class MediaSegment:
    URI: str
    Duration: float
    SegmentNum: int

    def __init__(self, segment: int, uri: str, duration: float):
        self.URI = uri
        self.Duration = duration
        self.SegmentNum = segment

    def __repr__(self):
        return (f"MediaSegment(SegmentNum={self.SegmentNum}, URI='{self.URI}', Duration={self.Duration}))")

    def __str__(self):
        return (f"Media Segment Info:\n"
                f"  SegmentNum: {self.SegmentNum}\n"
                f"  URI: {self.URI}\n"
                f"  Duration: {self.Duration} seconds")

class RenditionReport:
    URI: str
    Last_MSN: int = 0
    Last_Part: int = 0

    def __init__(self, uri: str, last_msn: int, last_part: int):
        self.URI = uri
        self.LastMSN = last_msn
        self.LastPart = last_part

    def __repr__(self):
        return (f"RenditionReport(URI='{self.URI}', "
                f"LastMSN={self.LastMSN}, LastPart={self.LastPart})")

class TypeM3U8(Enum):
    UNDEFINED = "UNDEFINED"
    MASTER = "MASTER"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    
    def __str__(self):
        return '%s' % self.value


class TypeDownload(Enum):
    UNDEFINED = "UNDEFINED"
    MANIFEST_MASTER = "MANIFEST_MASTER"
    MANIFEST_MEDIA = "MANIFEST_MEDIA"
    #MANIFEST_AUDIO = "MANIFEST_AUDIO"
    FILE_SEGMENT = "FILE_SEGMENT"
    FILE_INIT = "FILE_INIT"
    FILE_PART = "FILE_PART"

    def __str__(self):
        return '%s' % self.value
    
class M3U8:
    Type: TypeM3U8 = TypeM3U8.UNDEFINED
    EXT_X_Independent_Segments: bool
    EXT_X_Target_Duration: int
    EXT_X_Media_Sequence: int
    EXT_X_Map_URI: str
    EXT_X_Server_Control_Can_Block_Reload: bool
    EXT_X_Server_Control_Part_Hold_Back: float
    EXT_X_PartInf_Part_Target: float
    EXT_X_Preload_Hint_URI: str
    Media_Audios: List[MediaAudio]
    Media_Streams: List[MediaStream]
    Media_Parts: List[MediaPart]
    Media_Segments: List[MediaSegment]
    RenditionReports: List[RenditionReport]
    URI: str
    Name: str
    FileDownloaded: DownloadMetrics

    def __init__(self, type_m3u8: TypeM3U8):
        self.Type = type_m3u8
        self.EXT_X_Independent_Segments = False
        self.EXT_X_Target_Duration = 0
        self.EXT_X_Media_Sequence = 0
        self.EXT_X_Map_URI = ""
        self.EXT_X_Server_Control_Can_Block_Reload = False
        self.EXT_X_Server_Control_Part_Hold_Back = 0.0
        self.EXT_X_PartInf_Part_Target = 0.0
        self.Media_Audios: List[MediaAudio] = []
        self.Media_Streams: List[MediaStream] = []
        self.Media_Parts: List[MediaPart] = []
        self.Media_Segments: List[MediaSegment] = []
        self.RenditionReports: List[RenditionReport] = []
        self.URI = None
        self.Name = None
        self.FileDownloaded = None

    def __repr__(self):
        return (f"M3U8Wrapper(Type={self.Type}, "
                f"EXT_X_Independent_Segments={self.EXT_X_Independent_Segments}, "
                f"EXT_X_Target_Duration={self.EXT_X_Target_Duration}, "
                f"EXT_X_Media_Sequence={self.EXT_X_Media_Sequence}, "
                f"EXT_X_Map_URI='{self.EXT_X_Map_URI}', "
                f"EXT_X_Server_Control_Can_Block_Reload={self.EXT_X_Server_Control_Can_Block_Reload}, "
                f"EXT_X_Server_Control_Part_Hold_Back={self.EXT_X_Server_Control_Part_Hold_Back}, "
                f"EXT_X_PartInf_Part_Target={self.EXT_X_PartInf_Part_Target}, "
                f"Media_Audios={self.Media_Audios}, "
                f"Media_Streams={self.Media_Streams}, "
                f"Media_Parts={self.Media_Parts}, "
                f"Media_Segments={self.Media_Segments}, "
                f"RenditionReports={self.RenditionReports}, "
                f"URI={self.URI}, "
                f"Name={self.Name})")

def ensure_absolute_url(base_url: str, url: str):
    if not url or url=="":
        return ""
    
    # Parse the URL
    parsed_url = urlparse(url)

    # Check if the URL is absolute
    if parsed_url.scheme and parsed_url.netloc:
        # If both scheme and netloc (domain) are present, it's an absolute URL
        return url
    else:
        # If not, it’s a relative URL, combine it with the base URL
        return urljoin(base_url, url)

def download_file_http2(url, path_to_save: str = None) -> DownloadMetrics:
    global _client_h2
    
    parsed_url = urlparse(url)
    if parsed_url is None or not bool(parsed_url.path):
        return None

    filename = os.path.basename(parsed_url.path)
    query = "?" + parsed_url.query if parsed_url.query else ""
    #safe_print(f"Downloading: {filename + query}")

    save_file = path_to_save is not None
    
    # timer to measure response time
    timer_start: float = None    
    time_to_firstbyte_ms: float = 0.0
    time_to_get_headers_ms: float = 0.0
    timer_body_received: float = 0.0

    time_body_downloading_by_chunks_s: float = 0.0
    body_total_size: int = 0

    http_status: str = ""
    http_code: int = 0
    content = bytearray()
    download_speed = 0.0
    body_downloading_time_s = 0.0
    time_to_finish_ms = 0.0
    response_headers: List[tuple[str,str]] = []


    # Get headers
    #with httpx.Client(http2 = True) as client_h2:
    # _client_h2 is initialized globally, so new connections are reused by HTTP2 client
    if _client_h2:

        i_try = 2
        while i_try > 0:
            if i_try == 1:
                pass
            i_try -= 1

            try:
                # Start the timer to measure response time
                timer_start = time.time()

                if _client_h2.is_closed:
                    _client_h2 = init_client_h2()

                with _client_h2.stream("GET", url) as response_h2:
                    # Measure Time to First Byte (TTFB)
                    time_to_firstbyte_ms = time_to_get_headers_ms = (time.time() - timer_start) * 1000

                    ## Time to get headers (using elapsed time from response)
                    #time_to_firstbyte_ms = time_to_get_headers_ms = response_h2.elapsed.total_seconds() * 1000   – impossible to calculate in that library

                    # Get HTTP code
                    http_status = ""
                    http_code = response_h2.status_code
                    content_type = response_h2.headers.get('Content-Type', '')

                    headers_to_save = ["cache", "date", "content-type", "traceparent", "x-id", "x-id-fe"]
                    for h in response_h2.headers:
                        if h in headers_to_save:
                            response_headers.append((h, response_h2.headers.get(h)))
                    pass

                    #if True:
                    #    if random.randint(0, 100) > 70:
                    #        http_code = 599
                    
                    if http_code != 200:
                        #display.display_error(f"Failed to download. HTTP Status Code: {http_code}")
                        #print(f"Failed to download. HTTP Status Code: {http_code}")
                        return DownloadMetrics(http_code, f"ERROR {http_code}")
                    else:
                        http_status = "OK"

                    # Parse and check content-type
                    valid_content_types = ["application/vnd.apple.mpegurl", "application/x-mpegURL", "video/mp4"]
                    if content_type not in valid_content_types:
                        #display.display_error(f"Invalid Content-Type: {content_type}")
                        #print(f"Invalid Content-Type: {content_type}")
                        return DownloadMetrics(0, f"ERROR Invalid {content_type}", response_headers=response_headers)
                    else:
                        #safe_print("Valid Content-Type found:", content_type)
                        pass

                    # Calculate the size of the downloaded file
                    body_total_size = 0
                    time_body_downloading_by_chunks_s = 0.0

                    # Start the timer to measure the time to get the body
                    timer_body_start = timer_body_received = time.time()

                    # Download data, measure, and save the file
                    content = bytearray()
                    try:
                        file = None
                        if save_file:
                            file = open(path_to_save, 'wb')

                        timer_body_downloading = time.time()
                        for chunk in response_h2.iter_bytes(chunk_size = 10000000):
                            time_body_downloading_by_chunks_s += (time.time() - timer_body_downloading)
                            if chunk:
                                content.extend(chunk)
                                body_total_size += len(chunk)
                                if save_file:
                                    file.write(chunk)     
                    except Exception as e:
                        # Handle exceptions and print the error message
                        #print(f"An error occurred: {e}")
                        logs.write_exception(e)
                        if _client_h2:
                            _client_h2.close()

                        http_code = 0
                        http_status = f"ERROR {threading.current_thread().name} {e} i_try={i_try} {url}"
                        return DownloadMetrics(http_code, http_status, response_headers=response_headers)
                        #raise e
                    finally:
                        timer_body_received = time.time()
                        if file is not None:
                            file.close()
                
                #successefully downloaded
                i_try = 0
                break
            except Exception as e:
                # Handle exceptions and print the error message
                #print(f"ERROR: [{threading.current_thread().name} {e} i_try={i_try} {url}]")
                #raise e
                logs.write_exception(e)
                if _client_h2:
                    _client_h2.close()

                http_code = 0
                http_status = f"ERROR {threading.current_thread().name} {e} i_try={i_try} {url}"
                return DownloadMetrics(http_code, http_status, response_headers=response_headers)

    # Calculate total response time
    time_to_finish_ms = (timer_body_received - timer_start) * 1000
    
    # Calculate download speed of body only (as Safari and Chrome calculate it)
    ##downloading_time_s = (time_to_finish_ms - time_to_firstbyte_ms) / 1000
    #body_downloading_time_s = (timer_body_received -  timer_body_start)
    body_downloading_time_s = time_body_downloading_by_chunks_s
    if body_downloading_time_s > 0:
            # Get the size of the headers
            #headers_size = sum(len(k) + len(v) + 4 for k, v in response.headers.items()) + 4

            # Get the size of the body
            #body_size = len(response.content)

            #download_speed = (headers_size + body_total_size) * 8 / (downloading_time_s)
            download_speed = (body_total_size) * 8 / (body_downloading_time_s)
    else:
        download_speed = 0

    # Print all the metrics
    #print(f"HTTP code: {http_code}")
    #print(f"TTFB: {time_to_firstbyte_ms:.1f} ms")
    #print(f"Time to get headers: {time_to_get_headers_ms:.1f} ms")
    #print(f"Download body speed: {beautify_number(download_speed)} bps ({(download_speed/1000/1000):.1f} Mbps, {(download_speed/8/1000/1000):.1f} MB/s)")
    #print(f"Download body time: {downloading_time_s*1000:.1f} ms")
    #print(f"Total response time: {time_to_finish_ms:.1f} ms")
    
    metrics = DownloadMetrics(
        http_code=http_code,
        status=http_status,
        response_body=content,
        ttfb=time_to_firstbyte_ms,
        time_headers=time_to_get_headers_ms,
        download_speed=download_speed,
        downloading_time=body_downloading_time_s * 1000,
        response_time=time_to_finish_ms,
        response_headers=response_headers
    )

    return metrics



def download_file_http1(url, path_to_save: str = None) -> DownloadMetrics:
    parsed_url = urlparse(url)
    if parsed_url is None or not bool(parsed_url.path):
        return None

    filename = os.path.basename(parsed_url.path)
    query = "?" + parsed_url.query if parsed_url.query else ""
    #safe_print(f"Downloading: {filename + query}")

    save_file = path_to_save is not None
    
    # timer to measure response time
    timer_start : float = None    
    time_to_firstbyte_ms : float = 0
    time_to_get_headers_ms : float = 0

    http_status: str = ""
    http_code: int = 0
    content = bytearray()
    download_speed = 0.0
    body_downloading_time_s = 0.0
    time_to_finish_ms = 0.0
    response_headers: List[tuple[str,str]] = []

    # Perform the GET request
    response_h1: requests.Response = None
    try:
        # Start the timer to measure response time
        timer_start = time.time()

        response_h1 = requests.get(url, stream=True) #.__enter__()
        #response = requests.get(url)

        # Calculate the time to get headers
        timer_headers_received = time.time()
        time_to_get_headers_ms = (timer_headers_received - timer_start) * 1000

        # Measure Time to First Byte (TTFB)
        time_to_firstbyte_ms = response_h1.elapsed.total_seconds() * 1000

        # Get HTTP code
        http_code = response_h1.status_code

        #if True:
        #    if random.randint(0, 100) > 70:
        #        http_code = 598

        headers_to_save = ["cache", "date", "content-type", "traceparent", "x-id", "x-id-fe"]
        for h in response_h1.headers:
            if h.lower() in headers_to_save:
                response_headers.append((h.lower(), response_h1.headers.get(h)))
        pass

        if http_code != 200:
            #display.display_error(f"Failed to download. HTTP Status Code: {http_code}")
            #print(f"Failed to download. HTTP Status Code: {http_code}")
            #return None
            return DownloadMetrics(http_code, f"ERROR {http_code}", response_headers=response_headers)
        else:
            http_status = "OK"




        # Parse and check content-type
        content_type = response_h1.headers.get('Content-Type', '')
        valid_content_types = ["application/vnd.apple.mpegurl", "application/x-mpegURL", "video/mp4"]
        if content_type not in valid_content_types:
            #display.display_error(f"Invalid Content-Type: {content_type}")
            print(f"Invalid Content-Type: {content_type}")
            #return
            return DownloadMetrics(http_code, f"ERROR Invalid {content_type}", response_headers=response_headers)
        else:
            #safe_print("Valid Content-Type found:", content_type)
            pass



        # Calculate the size of the downloaded file
        body_total_size = 0
        time_body_downloading_by_chunks_s : float = 0

        # Start the timer to measure the time to get the body
        timer_body_start = timer_body_received = time.time()

        # Download data, measure, and save the file
        content = bytearray()
        try:
            file = None
            if save_file:
                file = open(path_to_save, 'wb')

            timer_body_downloading = time.time()
            #for chunk in response.iter_content():
            for chunk in response_h1.iter_content(chunk_size = None):
                time_body_downloading_by_chunks_s += (time.time() - timer_body_downloading)
                if chunk:
                    content.extend(chunk)
                    body_total_size += len(chunk)
                    if save_file:
                        file.write(chunk)

                #content = response.content
                #body_total_size += len(content)
                #if save_file:
                #    file.write(content)        
        except Exception as e:
            # Handle exceptions and print the error message
            print(f"An error occurred: {e}")
            logs.write_exception(e)
            http_code = 0
            http_status = f"ERROR {threading.current_thread().name} {e}"
            return DownloadMetrics(http_code, http_status, response_headers=response_headers)
        finally:
            timer_body_received = time.time()
            
            if file is not None:
                file.close()
                #safe_print(f"File saved successfully as {path_to_save}")
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"ERROR: [{threading.current_thread().name} {e}]")
        logs.write_exception(e)
        http_code = 0
        http_status = f"ERROR {threading.current_thread().name} {e}"
        return DownloadMetrics(http_code, http_status, response_headers=response_headers)

    #finally:
    #    #response_h1.close()   HTTP1 has no "close()" method


    # Calculate total response time
    time_to_finish_ms = (timer_body_received - timer_start) * 1000
    
    # Calculate download speed of body only (as Safari and Chrome calculate it)
    ##downloading_time_s = (time_to_finish_ms - time_to_firstbyte_ms) / 1000
    #body_downloading_time_s = (timer_body_received -  timer_body_start)
    body_downloading_time_s = time_body_downloading_by_chunks_s
    if body_downloading_time_s > 0:
            # Get the size of the headers
            #headers_size = sum(len(k) + len(v) + 4 for k, v in response.headers.items()) + 4

            # Get the size of the body
            #body_size = len(response.content)

            #download_speed = (headers_size + body_total_size) * 8 / (downloading_time_s)
            download_speed = (body_total_size) * 8 / (body_downloading_time_s)
    else:
        download_speed = 0

    # Print all the metrics
    #print(f"HTTP code: {http_code}")
    #print(f"TTFB: {time_to_firstbyte_ms:.1f} ms")
    #print(f"Time to get headers: {time_to_get_headers_ms:.1f} ms")
    #print(f"Download body speed: {beautify_number(download_speed)} bps ({(download_speed/1000/1000):.1f} Mbps, {(download_speed/8/1000/1000):.1f} MB/s)")
    #print(f"Download body time: {downloading_time_s*1000:.1f} ms")
    #print(f"Total response time: {time_to_finish_ms:.1f} ms")
    
    metrics = DownloadMetrics(
        http_code=http_code,
        status=http_status,
        response_body=content,
        ttfb=time_to_firstbyte_ms,
        time_headers=time_to_get_headers_ms,
        download_speed=download_speed,
        downloading_time=body_downloading_time_s * 1000,
        response_time=time_to_finish_ms,
        response_headers=response_headers
    )

    return metrics

def parse_m3u8(data: bytearray, master_url: str) -> M3U8:
    if data is None or len(data) == 0:
        return None

    # Convert bytearray to a string
    text_data = data.decode('utf-8')
    lines = text_data.splitlines()

    if len(lines) == 0:
        return None
    
    # Check the first line
    if lines[0].strip() != "#EXTM3U":
        #display.display_error(f"Invalid M3U8 file. First line: {lines[0]}")
        print(f"Invalid M3U8 file. First line: {lines[0]}")
        return None
    
    #print(f"Valid M3U8 file. First line: {lines[0]}")

    # Initialize variables
    params_independent_segments = False
    params_target_duration = 0
    params_part_target = 0.0
    params_media_sequence = 1
    params_map_uri = ""
    params_server_control_can_block_reload = False
    params_server_control_part_hold_back = 0.0
    media_parts_preload_hint_uri = ""
    media_rendition_reports : List[RenditionReport] = []
    media_audios: List[MediaAudio] = []
    media_streams : List[MediaStream] = []
    media_parts : List[MediaPart] = []
    media_segments : List[MediaSegment] = []

    previous_extinf : float = 0.0
    segment_num : int = params_media_sequence
    part_num : int = 0

    attr_pattern = r"=('([^']*)'|\"([^\"]*)\"|[^,\s]+)(?=,|$)"

    i = 1
    while i < len(lines):
        line = lines[i].strip()

        if line.startswith("#EXT-X-MEDIA:"):
            result_type = re.search(r'TYPE'+attr_pattern, line, re.IGNORECASE)
            if result_type is not None and result_type.group(1).upper() == "AUDIO":
                result_group_id = re.search(r'GROUP-ID'+attr_pattern, line, re.IGNORECASE)
                result_uri = re.search(r'URI'+attr_pattern, line, re.IGNORECASE)
                
                groupid = result_group_id.group(1).strip('\'"') if result_group_id else None
                url = result_uri.group(1).strip('\'"') if result_uri else None
                url = ensure_absolute_url(master_url, url)
                
                media_audios.append(MediaAudio(groupid, url))

        elif line.startswith("#EXT-X-STREAM-INF:"):
            if i + 1 < len(lines):
                parsed_filename = urlparse(lines[i + 1].strip())
                if bool(parsed_filename.path): 
                    result_bandwidth = re.search(r'BANDWIDTH=(\d+)', line, re.IGNORECASE)
                    result_resolution = re.search(r'RESOLUTION=([0-9x]+)', line, re.IGNORECASE)
                    result_audio = re.search(r'AUDIO'+attr_pattern, line, re.IGNORECASE)

                    bandwidth = int(result_bandwidth.group(1).strip('\'"')) if result_bandwidth else 0
                    resolution = result_resolution.group(1).strip('\'"') if result_resolution else None
                    audio = result_audio.group(1).strip('\'"') if result_audio else None

                    url = ensure_absolute_url(master_url, parsed_filename.geturl())

                    media_streams.append(MediaStream(url, bandwidth, resolution, audio))
                    i += 1

        elif line.startswith("#EXT-X-TARGETDURATION:"):
            result = re.search(r'#EXT-X-TARGETDURATION:(\d+)', line, re.IGNORECASE)
            if result:
                params_target_duration = int(result.group(1))

        elif line.startswith("#EXT-X-INDEPENDENT-SEGMENTS"):
            params_independent_segments = True

        elif line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            result = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', line, re.IGNORECASE)
            if result:
                params_media_sequence = segment_num = int(result.group(1))

        elif line.startswith("#EXT-X-MAP:"):
            result_uri = re.search(r'URI'+attr_pattern, line, re.IGNORECASE)
            if result_uri:
                params_map_uri = ensure_absolute_url(master_url, result_uri.group(1).strip('\'"'))

        elif line.startswith("#EXT-X-SERVER-CONTROL:"):
            can_block_reload = re.search(r'CAN-BLOCK-RELOAD=(\w+)', line, re.IGNORECASE)
            if can_block_reload:
                params_server_control_can_block_reload = can_block_reload.group(1).upper() == 'YES'
            part_hold_back = re.search(r'PART-HOLD-BACK=([\d.]+)', line, re.IGNORECASE)
            if part_hold_back:
                params_server_control_part_hold_back = float(part_hold_back.group(1))

        elif line.startswith("#EXT-X-PART-INF:"):
            part_target = re.search(r'PART-TARGET=([\d.]+)', line, re.IGNORECASE)
            if part_target:
                params_part_target = float(part_target.group(1))

        elif line.startswith("#EXT-X-PART:"):
            result_uri = re.search(r'URI'+attr_pattern, line, re.IGNORECASE)
            result_duration = re.search(r'DURATION=([\d.]+)', line, re.IGNORECASE)
            result_independent = re.search(r'INDEPENDENT=(\w+)', line, re.IGNORECASE)

            uri = result_uri.group(1).strip('\'"') if result_uri else ""
            duration = float(result_duration.group(1).strip('\'"')) if result_duration else 0.0
            independent = result_independent.group(1).upper() == 'YES' if result_independent else False

            url = ensure_absolute_url(master_url, uri)

            media_parts.append(MediaPart(segment_num, part_num, url, duration, independent))

            part_num += 1

        elif line.startswith("#EXT-X-PRELOAD-HINT:"):
            result_preload_type = re.search(r'TYPE'+attr_pattern, line, re.IGNORECASE)
            result_uri = re.search(r'URI'+attr_pattern, line, re.IGNORECASE)
            if result_preload_type and result_preload_type.group(1).strip('\'"').upper() == "PART":
                url = ensure_absolute_url(master_url, result_uri.group(1).strip('\'"') if result_uri else "")
                media_parts_preload_hint_uri = url

        elif line.startswith("#EXT-X-RENDITION-REPORT:"):
            result_uri = re.search(r'URI'+attr_pattern, line, re.IGNORECASE)
            result_last_msn = re.search(r'LAST-MSN=(\d+)', line, re.IGNORECASE)
            result_last_part = re.search(r'LAST-PART=(\d+)', line, re.IGNORECASE)

            rendition_uri = result_uri.group(1).strip('\'"') if result_uri else ""
            rendition_last_msn = int(result_last_msn.group(1).strip('\'"')) if result_last_msn else 0
            rendition_last_part = int(result_last_part.group(1).strip('\'"')) if result_last_part else 0

            url = ensure_absolute_url(master_url, rendition_uri)

            media_rendition_reports.append(RenditionReport(url, rendition_last_msn, rendition_last_part))

        elif line.startswith("#EXTINF:"):
            result_duration = re.search(r'#EXTINF:([\d.]+),?', line, re.IGNORECASE)
            if result_duration:
                previous_extinf = float(result_duration.group(1))

        elif len(line) == 0:
            pass
            
        elif not line.startswith("#"):
            parsed_filename = urlparse(line)
            if bool(parsed_filename.path):
                url = ensure_absolute_url(master_url, parsed_filename.geturl())
                
                media_segments.append(MediaSegment(segment_num, url, previous_extinf))
                
                previous_extinf = 0.0
                segment_num += 1
                part_num = 0
                if len(media_parts) > 0:
                    media_parts[len(media_parts)-1].Final = True
        i += 1

    manifest = None

    # Decide what type of manifest it is: master, media, etc:
    if len(media_streams) > 0:
        # It's master manifest
        manifest = M3U8(TypeM3U8.MASTER)
        manifest.EXT_X_Independent_Segments = params_independent_segments
        manifest.Media_Streams = media_streams
        manifest.Media_Audios = media_audios

    elif len(media_segments) > 0:
        # It's media manifest
        manifest = M3U8(TypeM3U8.VIDEO)
        manifest.EXT_X_Target_Duration = params_target_duration
        manifest.EXT_X_Independent_Segments = params_independent_segments
        manifest.EXT_X_Media_Sequence = params_media_sequence
        manifest.EXT_X_Map_URI = params_map_uri
        manifest.EXT_X_Server_Control_Can_Block_Reload = params_server_control_can_block_reload
        manifest.EXT_X_Server_Control_Part_Hold_Back = params_server_control_part_hold_back
        manifest.EXT_X_PartInf_Part_Target = params_part_target
        manifest.Media_Segments = media_segments
        manifest.Media_Parts = media_parts
        manifest.EXT_X_Preload_Hint_URI = media_parts_preload_hint_uri
        manifest.RenditionReports = media_rendition_reports

    return manifest

def load_and_parse_master(url: str, path_to_save: str = None) -> M3U8:
    parsed_url = urlparse(url)
    if parsed_url is None or not bool(parsed_url.path):
        return None
    
    file_metrics = download_file_http1(url, path_to_save)
    if file_metrics:
        #print(file_metrics)

        manifest = parse_m3u8(file_metrics.Response_body, parsed_url.geturl())

        if manifest:
            manifest.URI = parsed_url.geturl()
            manifest.Name = os.path.basename(parsed_url.path)
            manifest.FileDownloaded = file_metrics
            return manifest
        else:
            manifest = M3U8(TypeM3U8.UNDEFINED)
            manifest.URI = parsed_url.geturl()
            manifest.Name = os.path.basename(parsed_url.path)
            manifest.FileDownloaded = file_metrics
            return manifest
    return None

def load_and_parse_manifest(url: str, path_to_save: str = None) -> M3U8:
    status = ""
    try:
        parsed_url = urlparse(url)
        if parsed_url is None or not bool(parsed_url.path):
            return None

        #HTTP1
        file_metrics = download_file_http1(parsed_url.geturl(), path_to_save)        
        #HTTP2
        #file_metrics = download_file_http2(parsed_url.geturl(), path_to_save)
        if file_metrics is not None:
            #print(file_metrics)

            manifest = parse_m3u8(file_metrics.Response_body, parsed_url.geturl())

            if manifest:
                manifest.URI = parsed_url.geturl()
                manifest.Name = os.path.basename(parsed_url.path)
                manifest.FileDownloaded = file_metrics
                return manifest
            else:
                tmp = M3U8(TypeM3U8.UNDEFINED)
                tmp.URI = parsed_url.geturl()
                tmp.Name = os.path.basename(parsed_url.path)
                tmp.FileDownloaded = file_metrics
                return tmp
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")    
        logs.write_exception(e)
        status = str(e)
        #return None
    
    tmp = M3U8(TypeM3U8.UNDEFINED)
    tmp.URI = parsed_url.geturl()
    tmp.Name = os.path.basename(parsed_url.path)
    tmp.FileDownloaded = DownloadMetrics(0, f"ERROR {e}")
    return tmp

        
        
    





    