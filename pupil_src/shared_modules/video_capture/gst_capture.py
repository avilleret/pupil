'''
(*)~----------------------------------------------------------------------------------
 Pupil - eye tracking platform
 Copyright (C) 2012-2016  Pupil Labs

 Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0).
 License details are in the file license.txt, distributed as part of this software.
----------------------------------------------------------------------------------~(*)
'''

import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
import cv2
import numpy as np

from fake_capture import Fake_Capture

from ctypes import c_double
from pyglui import ui
from time import time
#logging
import logging
logger = logging.getLogger(__name__)

Gst.init(None)

class CameraCaptureError(Exception):
    """General Exception for this module"""
    def __init__(self, arg):
        super(CameraCaptureError, self).__init__()
        self.arg = arg

class Frame:
    def __init__(self, w, h):
        self.width = w
        self.height = h
        self.yuv_buffer = False
        self.bgr = np.zeros((h,w,3), np.uint8)
        self.gray = np.zeros((h,w), np.uint8)

    @property
    def img(self):
        return self.bgr


class Gst_Capture(object):
    """
    Camera Capture is a class that encapsualtes uvc.Capture:
     - adds UI elements
     - adds timestamping sanitization fns.
    """
    def __init__(self, port=5000, timebase=None):
        if timebase == None:
            logger.debug("Capture will run with default system timebase")
            self.timebase = c_double(0)
        elif hasattr(timebase,'value'):
            logger.debug("Capture will run with app wide adjustable timebase")
            self.timebase = timebase
        else:
            logger.error("Invalid timebase variable type. Will use default system timebase")
            self.timebase = c_double(0)

        self.sidebar = None
        self.menu = None
        self.port = port
        self.new_frame = False

        self.frame = Frame(640,480)
        self.init_capture()

    def re_init_capture(self):
        current_size = self.capture.frame_size
        current_fps = self.capture.frame_rate

        self.capture = None
        #recreate the bar with new values
        '''
        menu_conf = self.menu.configuration
        self.deinit_gui()
        self.init_capture(uid)
        self.frame_size = current_size
        self.frame_rate = current_fps
        self.init_gui(self.sidebar)
        self.menu.configuration = menu_conf
        '''

    def init_capture(self):

        self.ts_offset = -0.1 # Timestamp offset applied: -0.1sec
        # Create GStreamer elements
        self.gst_source = Gst.ElementFactory.make('udpsrc', None)
        self.gst_source.set_property('port', self.port)
        self.gst_buf = Gst.ElementFactory.make('rtpjitterbuffer',None)
        self.gst_depay = Gst.ElementFactory.make('rtph264depay', None)
        self.gst_decoder = Gst.ElementFactory.make('avdec_h264', None)
        self.gst_sink = Gst.ElementFactory.make("appsink", "sink")

        # Create the empty pipeline
        self.gst_pipeline = Gst.Pipeline.new("test-pipeline")

        if not self.gst_source or not self.gst_sink or not self.gst_pipeline or not self.gst_buf or not self.gst_depay or not self.gst_decoder or not self.gst_sink:
            print("Not all elements could be created.")

        self.gst_sink.set_property("emit-signals", True)

        self.gst_sink.connect("new-sample", self.new_buffer, self.gst_sink)

        # add elements to the pipeline
        self.gst_pipeline.add(self.gst_source)
        self.gst_pipeline.add(self.gst_buf)
        self.gst_pipeline.add(self.gst_depay)
        self.gst_pipeline.add(self.gst_decoder)
        self.gst_pipeline.add(self.gst_sink)


        self.gst_source.link_filtered(self.gst_depay, Gst.caps_from_string("application/x-rtp, payload=96"))
        self.gst_depay.link(self.gst_decoder)
        self.gst_decoder.link(self.gst_sink)

        # Start playing
        ret = self.gst_pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            print("Unable to set the pipeline to the playing state.")

        # Wait until error or EOS
        bus = self.gst_pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message::error', self.on_error)

    def gst_to_opencv(self, sample):
        buf = sample.get_buffer()
        caps = sample.get_caps()
        # print caps.get_structure(0).get_value('format')
        # print caps.get_structure(0).get_value('height')
        # print caps.get_structure(0).get_value('width')

        # print buf.get_size()

        fmt = caps.get_structure(0).get_value('format')
        w = caps.get_structure(0).get_value('width')
        h = caps.get_structure(0).get_value('height')
        size = w*h

        self.frame.width = w
        self.frame.height = h

        if fmt == 'I420':
            buf=sample.get_buffer()
            #extract data stream as string
            data=buf.extract_dup(0,buf.get_size())

            stream=np.fromstring(data,np.uint8) #convert data form string to numpy array

            #Y bytes  will start form 0 and end in size-1
            y=stream[0:size].reshape(h,w) # create the y channel same size as the image

            #U bytes will start from size and end at size+size/4 as its size = framesize/4
            u=stream[size:(size+(size/4))].reshape((h/2),(w/2))# create the u channel  itssize=framesize/4

            #up-sample the u channel to be the same size as the y channel and frame using pyrUp func in opencv2
            u_upsize=cv2.pyrUp(u)

            #do the same for v channel
            v=stream[(size+(size/4)):].reshape((h/2),(w/2))
            v_upsize=cv2.pyrUp(v)

            #create the 3-channel frame using cv2.merge func watch for the order
            yuv=cv2.merge((y,u_upsize,v_upsize))

            #Convert TO RGB format
            bgr=cv2.cvtColor(yuv,cv2.cv.CV_YCrCb2RGB) # strange to call it bgr while it's RGB
            self.frame.bgr = np.copy(bgr)
            self.frame.gray = np.copy(y)
            # logger.warning("new frame")
            self.new_frame = True
        else:
            logger.error("format %s not supported"%(fmt))


    def new_buffer(self, sink, data):
        global image_arr
        sample = sink.emit("pull-sample")
        # buf = sample.get_buffer()
        # print "Timestamp: ", buf.pts
        self.gst_to_opencv(sample)
        return Gst.FlowReturn.OK

    def on_error(self, bus, msg):
        print('on_error():', msg.parse_error())

    def get_frame(self):
        self.timestamp = self.get_now()+self.ts_offset
        self.timestamp -= self.timebase.value
        self.frame.timestamp = self.timestamp

        # block until we get a new frame
        # this leads to a non-constant framerate which is annoying
        #while self.new_frame != True:
        #    pass

        self.new_frame = False
        return self.frame # TODO copy before return ?

    def get_now(self):
        return time()

    def get_timestamp(self):
        return self.get_now()-self.timebase.value

    @property
    def name(self):
        return 'gst:' + str(self.port)

    @property
    def jpeg_support(self):
        return False

    def init_gui(self,sidebar):
        pass

    def deinit_gui(self):
        pass

    def close(self):
        self.deinit_gui()
        # Free gst resources
        pipeline.set_state(Gst.State.NULL)
        logger.info("Capture released")
    @property
    def frame_rate(self):
        return 60
    @property
    def settings(self):
        settings = {}
        settings['name'] = self.capture.name
        settings['frame_rate'] = self.frame_rate
        settings['frame_size'] = self.frame_size
        return settings
    @settings.setter
    def settings(self,settings):
        pass # all gstreamer parameters are set by the pipeline (on both side)
    @frame_rate.setter
    def frame_rate(self,new_rate):
        pass
    @property
    def frame_size(self):
        return self.capture.frame_size
    @frame_size.setter
    def frame_size(self,new_size):
        pass



