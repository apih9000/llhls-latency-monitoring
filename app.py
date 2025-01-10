import argparse
import display
import logs
import m3u8
import monitoring

class EnableBooleanAction(argparse.Action):
    def __init__(self, option_strings, dest, nargs=None, **kwargs):
        if nargs is not None:
            raise ValueError("nargs not allowed")
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)

def main(url: str, limit: int, speed_limit: int, save_files: str):

#    print(f"Found: {master_playlist.Type}, {master_playlist.Name}, {master_playlist.URI}")
#
#    for i, stream in enumerate(master_playlist.Media_Streams):
#        print(f'Stream {i + 1}: ' +  str(stream))
#
#    for i, stream in enumerate(master_playlist.Media_Audios):
#        print(f'Audio {i + 1}: ' +  str(stream))
    
    
    logs.init_logs()
    
    try:
        master_playlist = m3u8.load_and_parse_master(url)

        # Check if it is indeed a master playlist
        if master_playlist is None:
            #raise ValueError('The provided m3u8 file is not a master playlist or cannot be downloaded (see logs).')
            logs.write_error(f"Master manifest ({url}) is not an URL or cannot be loaded.")
            print(f'The provided m3u8 file ({url}) is not a master playlist or cannot be downloaded (see logs).')
            return
        elif master_playlist.Type == m3u8.TypeM3U8.MASTER:
            pass
        elif master_playlist.Type == m3u8.TypeM3U8.VIDEO:
            #create a fake master playlist
            master_playlist.Type = m3u8.TypeM3U8.MASTER
            master_playlist.Media_Streams.append(m3u8.MediaStream(master_playlist.URI, 0, "Undefined", "Undefined"))
            logs.write_warning(f"Provided manifest ({url}) is a media manifest instead of master. So will be used as master with 1 stream inside.")
        else:
            # if status != 200 or type is other that manifest
            msg = f"Master manifest ({url}) is not an URL of manifest or cannot be loaded. Status = {master_playlist.FileDownloaded.HTTP_code}, {master_playlist.FileDownloaded.Status}"
            logs.write_error(msg)
            print(msg)
            return

        if master_playlist.Type == m3u8.TypeM3U8.MASTER and len(master_playlist.Media_Streams)>0:
            display.init_display(master_playlist, limit)
            monitoring.coordinator(master_playlist, limit)
            display.display_getch(True)
            display.display_finish()
            monitoring.display_summary(master_playlist)
        pass
    except Exception as e:
        # Handle exceptions and print the error message
        print(f"An error occurred: {e}")
        logs.write_exception(e)
    finally:
        display.display_finish()

    




if __name__ == "__main__":
    # Create the parser
    parser = argparse.ArgumentParser(description="Script to handle URL, speed-limit, and save-files parameters")

    # Add the URL parameter (required, without modifiers)
    parser.add_argument('URL', type=str, help='Manifest URL .m3u8 (required)')

    # Add the speed-limit parameter (optional, with default value of 0)
    parser.add_argument('--limit', type=int, default=100, help='limit on the number of download repetitions (integer, default is 100)')

    # Add the speed-limit parameter (optional, with default value of 0)
    parser.add_argument('--speed-limit', type=int, default=0, help='Speed limit in Kbps (integer, default is 0) – not implemented')

    # Add the save-files parameter (optional boolean, default value is True)
    parser.add_argument('--save-files', action=EnableBooleanAction, default=False, help='Flag to save files (default is False) – not implemented')

    # Parse the arguments
    args = parser.parse_args()

    # Access the arguments
    url = args.URL
    limit = args.limit
    speed_limit = args.speed_limit
    save_files = args.save_files

    #url = "https://demo.gvideo.io/cmaf/2675_19146/master.m3u8"
    #url = "https://demo.gvideo.io/cmaf/2675_19146/media_0.m3u8"
    #limit = 100
    #speed_limit = 0
    #save_files = False

    # Print the values
    print(f'URL: {url}')
    print(f'Limit: {limit}')
    print(f'Speed limit: {speed_limit} Kbps – not implemented')
    print(f'Save files: {save_files} – not implemented')

    #Start
    main(url, limit, speed_limit, save_files)