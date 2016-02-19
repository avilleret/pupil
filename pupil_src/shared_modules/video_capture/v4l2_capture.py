'''
(*)~----------------------------------------------------------------------------------
 Pupil - eye tracking platform
 Copyright (C) 2012-2016  Pupil Labs

 Distributed under the terms of the GNU Lesser General Public License (LGPL v3.0).
 License details are in the file license.txt, distributed as part of this software.
----------------------------------------------------------------------------------~(*)
'''

import v4l2
from v4l2 import list_devices
#check versions for our own depedencies as they are fast-changing

from fake_capture import Fake_Capture

from ctypes import c_double
from pyglui import ui
from time import time
#logging
import logging
logger = logging.getLogger(__name__)

class CameraCaptureError(Exception):
    """General Exception for this module"""
    def __init__(self, arg):
        super(CameraCaptureError, self).__init__()
        self.arg = arg


class Camera_Capture(object):
    """
    Camera Capture is a class that encapsualtes v4l2.Capture:
     - adds UI elements
     - adds timestamping sanitization fns.
    """
    def __init__(self,uid,timebase=None):
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
        self.init_capture(uid)


    def re_init_capture(self,uid):
        current_size = self.capture.frame_size
        current_fps = self.capture.frame_rate

        self.capture = None
        #recreate the bar with new values
        menu_conf = self.menu.configuration
        self.deinit_gui()
        self.init_capture(uid)
        self.frame_size = current_size
        self.frame_rate = current_fps
        self.init_gui(self.sidebar)
        self.menu.configuration = menu_conf


    def init_capture(self,uid):
        self.uid = uid

        logger.info('open uid : %s', uid)

        if uid is not None:
            self.capture = v4l2.Capture(uid)
        else:
            self.capture = Fake_Capture()

        # if 'C930e' in self.capture.name:
        #        logger.debug('Timestamp offset for c930 applied: -0.1sec')
        #        self.ts_offset = -0.1
        # else:
        #    self.ts_offset = 0.0


        #v4l2 setting quirks:
        # controls_dict = dict([(c.display_name,c) for c in self.capture.controls])
        # try:
        #     controls_dict['Auto Focus'].value = 0
        # except KeyError:
        #     pass
#
        # if "Pupil Cam1" in self.capture.name or "USB2.0 Camera" in self.capture.name:
        #     self.capture.bandwidth_factor = 1.8
        #     if "ID0" in self.capture.name or "ID1" in self.capture.name:
        #         self.capture.bandwidth_factor = 1.3
        #         try:
        #             controls_dict['Auto Exposure Priority'].value = 1
        #         except KeyError:
        #             pass
        #         try:
        #             controls_dict['Saturation'].value = 0
        #         except KeyError:
        #             pass
        #         try:
        #             controls_dict['Absolute Exposure Time'].value = 63
        #         except KeyError:
        #             pass
        #     try:
        #         controls_dict['Auto Focus'].value = 0
        #     except KeyError:
        #         pass


    def get_frame(self):
        try:
            frame = self.capture.get_frame_robust()
        except:
            raise CameraCaptureError("Could not get frame from %s"%self.uid)

        # timestamp = self.get_now()+self.ts_offset
        timestamp = self.get_now()
        timestamp -= self.timebase.value
        frame.timestamp = timestamp
        return frame

    def get_now(self):
        return v4l2.get_sys_time_monotonic()

    def get_timestamp(self):
        return self.get_now()-self.timebase.value

    @property
    def frame_rate(self):
        return self.capture.frame_rate
    @frame_rate.setter
    def frame_rate(self,new_rate):
        #closest match for rate
        # rates = [ abs(r-new_rate) for r in self.capture.frame_rates ]
        # best_rate_idx = rates.index(min(rates))
        # rate = self.capture.frame_rates[best_rate_idx]
        # if rate != new_rate:
        #   logger.warning("%sfps capture mode not available at (%s) on '%s'. Selected %sfps. "%(new_rate,self.capture.frame_size,self.capture.name,rate))
        # self.capture.frame_rate = rate
        return


    @property
    def settings(self):
        settings = {}
        settings['name'] = self.capture.name
        settings['frame_rate'] = self.frame_rate
        settings['frame_size'] = self.frame_size
        settings['v4l2_controls'] = {}
        settings.update(self.capture.enum_controls)
        #for key, value in self.capture.enum_controls.iteritems():
        #for c in self.capture.enum_controls:
        #   settings['v4l2_controls'][key] = value
        return settings
    @settings.setter
    def settings(self,settings):
        self.frame_size = settings['frame_size']
        self.frame_rate = settings['frame_rate']
        # for c in self.capture.enum_controls:
        #control_dict = self.capture.enum_controls
        #for key, value in control_dict:
        #    try:
        #        value = settings['v4l2_controls'][key]
        #    except KeyError as e:
        #        logger.info('No v4l2 setting "%s" found from settings.'%key)
    @property
    def frame_size(self):
        return self.capture.frame_size
    @frame_size.setter
    def frame_size(self,new_size):
        #closest match for size
        sizes = [ abs(r[0]-new_size[0]) for r in self.capture.frame_sizes ]
        best_size_idx = sizes.index(min(sizes))
        size = self.capture.frame_sizes[best_size_idx]
        if size != new_size:
            logger.warning("%s resolution capture mode not available. Selected %s."%(new_size,size))
        self.capture.frame_size = size

    @property
    def name(self):
        # return self.capture.dev_name
        return "/dev/video0"


    @property
    def jpeg_support(self):
        if self.capture.__class__ is Fake_Capture:
            return False
        else:
            return True

    def init_gui(self,sidebar):

        #lets define some  helper functions:
        def gui_load_defaults():
            for c in self.capture.controls:
                try:
                    c.value = c.def_val
                except:
                    pass
        def set_size(new_size):
            self.frame_size = new_size
            menu_conf = self.menu.configuration
            self.deinit_gui()
            self.init_gui(self.sidebar)
            self.menu.configuration = menu_conf


        def gui_update_from_device():
            for c in self.capture.controls:
                c.refresh()

        def gui_init_cam_by_uid(requested_id):
            if requested_id is None:
                self.re_init_capture(None)
            else:
                for cam in v4l2.list_devices():
                    if cam['uid'] == requested_id:
                        # if is_accessible(requested_id):
                        self.re_init_capture(requested_id)
                        #else:
                        #    logger.error("The selected Camera is already in use or blocked.")
                        return
                logger.warning("could not reinit capture, src_id not valid anymore")
                return

        #create the menu entry
        self.menu = ui.Growing_Menu(label='Camera Settings')
        cameras = v4l2.list_devices()
        camera_names = ['Fake Capture']+[c['dev_name'] for c in cameras]
        camera_ids = [None]+[c['dev_path'] for c in cameras]
        self.menu.append(ui.Selector('uid',self,selection=camera_ids,labels=camera_names,label='Capture Device', setter=gui_init_cam_by_uid) )

        sensor_control = ui.Growing_Menu(label='Sensor Settings')
        sensor_control.append(ui.Info_Text("Do not change these during calibration or recording!"))
        sensor_control.collapsed=False
        image_processing = ui.Growing_Menu(label='Image Post Processing')
        image_processing.collapsed=True

        sensor_control.append(ui.Selector('frame_size',self,setter=set_size, selection=self.capture.frame_sizes,label='Resolution' ) )
        sensor_control.append(ui.Selector('frame_rate',self, selection=self.capture.frame_rates,label='Framerate' ) )

        for control in self.capture.enum_controls():
            c = None
            ctl_name = control['name']

            #now we add controls
            if control['type'] == 'bool' :
                c = ui.Switch('value',control,label=ctl_name, on_val=control['max'], off_val=control['min'])
            elif control['type'] == 'int':
                c = ui.Slider('value',control,label=ctl_name,min=control['min'],max=control['max'],step=control['step'])
            elif control['type'] == 'menu':
                selection = [value for name,value in control['menu'].iteritems() ]
                labels =    [name  for name,value in control['menu'].iteritems() ]
                c = ui.Selector('value',control, label = ctl_name, selection=selection,labels = labels)
            else:
                pass
            # if control['disabled']:
            #     c.read_only = True
            # if ctl_name == 'Exposure, Auto Priority':
            #     # the controll should always be off. we set it to 0 on init (see above)
            #     c.read_only = True

            # if c is not None:
            #     if control.unit == 'processing_unit':
            #         image_processing.append(c)
            #     else:
            #         sensor_control.append(c)
            sensor_control.append(c)

        self.menu.append(sensor_control)
        if image_processing.elements:
            self.menu.append(image_processing)
        self.menu.append(ui.Button("refresh",gui_update_from_device))
        self.menu.append(ui.Button("load defaults",gui_load_defaults))

        self.sidebar = sidebar
        #add below general settings
        self.sidebar.insert(1,self.menu)


    def deinit_gui(self):
        if self.menu:
            self.sidebar.remove(self.menu)
            self.menu = None


    def close(self):
        self.deinit_gui()
        # self.capture.close()
        del self.capture
        logger.info("Capture released")


