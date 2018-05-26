# requires pyusb
#   pip install --pre pyusb

import usb.core
import usb.util
import sys
import time
import fibre.protocol

# Currently we identify fibre-enabled devices by VID,PID
WELL_KNOWN_VID_PID_PAIRS = [
  (0x1209, 0x0D31),
  (0x1209, 0x0D32),
  (0x1209, 0x0D33)
]

def noprint(x):
  pass

class USBBulkTransport(fibre.protocol.PacketSource, fibre.protocol.PacketSink):
  def __init__(self, dev, printer=noprint):
    self.dev = dev
    self._name = "USB device {}:{}".format(dev.idVendor, dev.idProduct)

  ##
  # information about the connected device
  ##
  def info(self):
    # loop through configurations
    string = ""
    for cfg in self.dev:
      string += "ConfigurationValue {0}\n".format(cfg.bConfigurationValue)
      for intf in cfg:
        string += "\tInterfaceNumber {0},{0}\n".format(intf.bInterfaceNumber, intf.bAlternateSetting)
        for ep in intf:
          string += "\t\tEndpointAddress {0}\n".format(ep.bEndpointAddress)
    return string

  def init(self, printer=noprint):
    # detach kernel driver
    try:
      if self.dev.is_kernel_driver_active(1):
        self.dev.detach_kernel_driver(1)
        printer("Detached Kernel Driver\n")
    except NotImplementedError:
      pass #is_kernel_driver_active not implemented on Windows
    # set the active configuration. With no arguments, the first
    # configuration will be the active one
    self.dev.set_configuration()
    # get an endpoint instance
    self.cfg = self.dev.get_active_configuration()
    self.intf = self.cfg[(1,0)]
    # write endpoint
    self.epw = usb.util.find_descriptor(self.intf,
        # match the first OUT endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_OUT
    )
    assert self.epw is not None
    printer("EndpointAddress for writing {}\n".format(self.epw.bEndpointAddress))
    # read endpoint
    self.epr = usb.util.find_descriptor(self.intf,
        # match the first IN endpoint
        custom_match = \
        lambda e: \
            usb.util.endpoint_direction(e.bEndpointAddress) == \
            usb.util.ENDPOINT_IN
    )
    assert self.epr is not None
    printer("EndpointAddress for reading {}\n".format(self.epr.bEndpointAddress))

  def shutdown(self):
    return 0

  def process_packet(self, usbBuffer):
    try:
      ret = self.epw.write(usbBuffer, 0)
      return ret
    except usb.core.USBError as ex:
      if ex.errno == 19: # "no such device"
        raise fibre.protocol.ChannelBrokenException()
      else:
        raise

  def get_packet(self, deadline):
    try:
      bufferLen = self.epr.wMaxPacketSize
      timeout = max(int((deadline - time.monotonic()) * 1000), 0)
      ret = self.epr.read(bufferLen, timeout)
      return ret
    except usb.core.USBError as ex:
      if ex.errno == 19: # "no such device"
        raise fibre.protocol.ChannelBrokenException()
      else:
        raise

  def send_max(self):
    return 64

  def receive_max(self):
    return 64


def channel_from_usb_device(usb_device, printer=noprint, device_stdout=noprint):
    """
    Inits a Fibre Protocol channel from a PyUSB device object.
    """
    bulk_device = fibre.usbbulk_transport.USBBulkTransport(usb_device, printer)
    printer(bulk_device.info())
    bulk_device.init(printer)
    return fibre.protocol.Channel(
            "USB device bus {} device {}".format(usb_device.bus, usb_device.address),
            bulk_device, bulk_device,
            device_stdout)

def find_usb_channels(vid_pid_pairs=WELL_KNOWN_VID_PID_PAIRS, printer=noprint, device_stdout=noprint):
    """
    Scans for compatible USB devices.
    Returns a generator of fibre.protocol.Channel objects.
    """
    for vid_pid_pair in vid_pid_pairs:
        for usb_device in usb.core.find(idVendor=vid_pid_pair[0], idProduct=vid_pid_pair[1], find_all=True):
            printer("Found Fibre Hub via PyUSB")
            try:
                yield channel_from_usb_device(usb_device, printer, device_stdout)
            except usb.core.USBError as ex:
                if ex.errno == 13:
                    printer("USB device access denied. Did you set up your udev rules correctly?")
                    continue
                raise

def open_usb(bus, address, printer=noprint, device_stdout=noprint):
    usb_device1 = usb.core.find(bus=1, address=16)
    usb_device = usb.core.find(bus=bus, address=address)
    if usb_device is None:
        raise fibre.protocol.DeviceInitException("No USB device found on bus {} device {}".format(bus, address))
    channel = channel_from_usb_device(usb_device, printer, device_stdout)
    return object_from_channel(channel, printer)