import logging
import logging.handlers
from datetime import datetime
import os
import sys
import threading
import traceback
import atexit

from httpx import ProtocolError, RequestError

_logger: logging.Logger = None

def init_logs():
    global _logger

    # Setup logger
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = f"ll-hls-log_{current_time}.log"
    log_directory = "logs/"
    # logging.basicConfig(filename=log_filename,
    #                 filemode='a',
    #                 format='%(asctime)s.%(msecs)03d,%(levelname)s,%(message)s',
    #                 datefmt='%Y-%m-%d %H:%M:%S',
    #                 level=logging.INFO)
    
    l = logging.getLogger("ll-hls")
    l.setLevel(logging.INFO)
    l.handlers.clear()    
    os.makedirs(log_directory, exist_ok=True)
    h = logging.FileHandler(log_directory + log_filename, "a")
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter(fmt='%(asctime)s.%(msecs)03d,%(levelname)s,%(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    l.addHandler(h)

    # l.debug("This is a debug message")
    # l.info("This is an info message")
    # l.warning("This is a warning message")
    # l.error("This is an error message")
    # l.exception("This is an exception message")
    # l.critical("This is a critical message")

    _logger = l
    pass


# Function to handle uncaught exceptions
def log_uncaught_exceptions(ex_cls, ex, tb):
    _logger.critical(''.join(traceback.format_tb(tb)))
    _logger.critical(f'{ex_cls.__name__}: {ex}')

sys.excepthook = log_uncaught_exceptions

# Function to close all log handlers on exit
def close_log_handlers():
    global _logger

    #_logger.info("Shutting down logging system.")
    for handler in _logger.handlers:
        handler.close()
        _logger.removeHandler(handler)

atexit.register(close_log_handlers)


def escape_comma(obj: tuple) -> str:
    text = ""
    if isinstance(obj, str):
        text = obj.replace(',', '.')
    elif isinstance(obj, tuple):
        escaped_elements = []
        for element in obj:
            escaped_elements.append(str(element).replace(',', '.'))
        text = ",".join(escaped_elements)   
    else:
        text = str(obj)
        text = text.replace(',', '.')
    return text

def write_info(obj: tuple):
    global _logger

    text = escape_comma(obj)
    _logger.info(text)

def write_warning(obj: tuple):
    global _logger

    text = escape_comma(obj)
    _logger.warning(text)

def write_error(obj: tuple):
    global _logger

    text = escape_comma(obj)
    _logger.error(text)

def write_exception(e):
    global _logger

    # threading.current_thread().name,
    if isinstance(e, ProtocolError):
        _logger.error(",\"%s %s %s %s %s\"", type(e), e, e.args, e.request, threading.current_thread().name) 
        #_logger.error("This is an ProtocolError error message")
        pass
    if isinstance(e, RequestError):
        _logger.error(",\"%s %s %s %s %s\"", type(e), e, e.args, e.request, threading.current_thread().name)
        #_logger.error("This is an RequestError error message")
        pass
    elif isinstance(e, Exception):
        _logger.exception(",\"%s %s %s %s\"", type(e), e, e.args, threading.current_thread().name, exc_info=True, stack_info=True, stacklevel=1)
        #_logger.error("This is an Exception error message")
        pass
    else:
        _logger.exception(",\"%s %s %s\"", type(e), e, threading.current_thread().name, exc_info=True, stack_info=True)
        #_logger.error("This is an general error message")
        pass
    

