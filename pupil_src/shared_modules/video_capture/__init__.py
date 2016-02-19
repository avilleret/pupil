'''
(*)~----------------------------------------------------------------------------------
 Pupil - eye tracking platform
 Copyright (C) 2012-2016  Pupil Labs

 Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0).
 License details are in the file license.txt, distributed as part of this software.
----------------------------------------------------------------------------------~(*)
'''

"""
video_capture is a module that extends opencv's camera_capture for mac and windows
on Linux it repleaces it completelty.
it adds some fuctionalty like:
    - access to all uvc controls
    - assosication by name patterns instead of id's (0,1,2..)
it requires:
    - opencv 2.3+
    - on Linux: v4l2-ctl (via apt-get install v4l2-util)
    - on MacOS: uvcc (binary is distributed with this module)
"""
import os,sys
import cv2
import numpy as np
from os.path import isfile
from time import time

import platform
os_name = platform.system()
del platform

#logging
import logging
logger = logging.getLogger(__name__)


###OS specific imports and defs
if os_name in ("Linux","Darwin"):
    from uvc_capture import Camera_Capture,device_list,CameraCaptureError,is_accessible
    from gst_capture import Gst_Capture
elif os_name == "Windows":
    from win_video import Camera_Capture,device_list,CameraCaptureError
    def is_accessible(uid):
        return True
else:
    raise NotImplementedError()

if os_name == "Linux":
   from v4l2_capture import Camera_Capture as v4l2_Camera_Capture
   from v4l2_capture import list_devices as v4l2_device_list
   from v4l2_capture import CameraCaptureError as v4l2_CameraCaptureError

from av_file_capture import File_Capture, FileCaptureError, EndofVideoFileError,FileSeekError


def autoCreateCapture(src,timestamps=None,timebase = None):
    '''
    src can be one of the following:
     - a path to video file
     - patter of name matches
     - a device index
     - a Gst_Capture instance
     - None
    '''

    # video source
    if type(src) is str and os.path.isfile(src):
        return File_Capture(src,timestamps=timestamps)

    # live src - select form idx
    if type(src) == int:
        try:
            uid = device_list()[src]['uid']
        except IndexError:
            logger.warning("UVC Camera at index:'%s' not found."%src)
            src = None
        else:
            if is_accessible(uid):
                logger.info("UVC Camera with id:'%s' selected."%src)
                return Camera_Capture(uid,timebase=timebase)
            else:
                logger.warning("Camera selected by id matches is found but already in use")
                src = None

    # live src - select form pattern
    elif type(src) in (list,tuple):
        for name_pattern in src:
            # v4l2 device name starts with v4l2:
            if name_pattern[:5] == 'v4l2:':
                uid = name_pattern[5:]
                try:
                    cap = v4l2_Camera_Capture(uid,timebase=timebase)
                except Exception:
                    logger.warning("Error while opening device %s.", uid)
                else:
                    return cap
            if name_pattern[:4] == 'gst:':
                port = int(name_pattern[4:])
                logger.warning("Try to open gstreamer on port %s",port)
                # try:
                #     cap = Gst_Capture(port)
                # except Exception:
                #     logger.warning("Error while opening gstreamer on port %s.", port)
                # else:
                #     return cap
                return Gst_Capture(port)

        src = uid_from_name(src)

    # fake capture
    if src is None:
        logger.warning("Starting with Fake_Capture.")
    else:
        logger.warning("Starting with device %s.", src)

    return Camera_Capture(src,timebase=timebase)



def uid_from_name(pattern):
    # looking for attached cameras that match the suggested names
    # give precedence to camera that matches the first pattern in list.
    matching_devices = []
    attached_devices = device_list()
    logger.warning("Device list : ")
    logger.warning(attached_devices)
    for name_pattern in pattern:
        for device in attached_devices:
            if name_pattern in device['name']:
                if is_accessible(device['uid']):
                    return device['uid']
                else:
                    logger.warning("Camera '%s' matches the pattern but is already in use"%device['name'])
    logger.error('No accessible device found that matched %s'%pattern)


