# Import libraries
from kasa.iot import iotdevice
import asyncio  # async io
import platform  # platform
import argparse  # argument parsing
import json
import re  # regex
import logging  # Logging
from pathlib import Path  # Path functions

# Set platform policy
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set a default command response timeout (in seconds)
command_timeout_default = 3

# List of valid device command options
command_options = ['on', 'off', 'hw-info', 'status']

# CMD Line Parser
parser = argparse.ArgumentParser(description='Control a TP-Link Kasa Smart Device.')
parser.add_argument('--ip', help='The IP address of the device', required=True)
parser.add_argument('--children',
                    help='Zero-based, comma-separated list of child devices to target (for devices like power strips).'
                         'Example: 0,1,2',
                    default='all')
parser.add_argument('--command', help='Command to run', choices=command_options, required=True)
parser.add_argument('--timeout', type=int,
                    help='Timeout for command (in seconds)', default=command_timeout_default)
parser.add_argument('--log', help='File path for log file. Defaults to script folder if omitted')
parser.add_argument('--debug', type=bool, help='Verbose mode for debugging', nargs='?', const=True)

# Get CMD Args
args = parser.parse_args()
logLevel = logging.DEBUG if args.debug else logging.INFO

# Initialize logger (so functions can utilize it)
loggerName = "myLogger"
logPath = args.log if args.log else "."
logger = logging.getLogger(loggerName)


# Class for exceptions from the TpLinkKasaDevice class
class TpLinkKasaDeviceException(Exception):
    pass

# Class for hardware info for TP-Link Kasa Smart Device
class TpLinkKasaDeviceHardwareInfo:
    def __init__(self, hw_info):
        self.sw_version = hw_info.get('sw_ver')
        self.hw_version = hw_info.get('hw_ver')
        self.mac_address = hw_info.get('mac')
        self.type = hw_info.get('mic_type')
        self.hw_id = hw_info.get('hwId')
        self.oem_id = hw_info.get('oemId')

    def __str__(self):
        return "Type: {} | Software Ver: {} | Hardware Ver: {} | MAC Address: {}".format(
            self.type, self.sw_version, self.hw_version, self.mac_address)

# Class to wrap a TP-Link Kasa Smart Device
class TpLinkKasaDevice:
    def __init__(self, ip: str, iot_device: iotdevice.Device = None, logger: logging.Logger = None):
        self.ip = ip
        self.iot_device = iot_device
        self._logger = logger

    def __str__(self):
        return 'IP: {} | Name: {} | Device Type: {}'.format(
                self.ip, self.iot_device.alias, self.iot_device.device_type)

    @staticmethod
    async def connect(ip: str, logger: logging.Logger = None):
        # Connect to the Kasa device
        iot_device = await iotdevice.Device.connect(host=ip)

        # If the device connection was successful, create an object to wrap it
        #  and return the wrapper object
        if iot_device:
            kasa_device = TpLinkKasaDevice(ip)
            kasa_device.iot_device = iot_device
            kasa_device._logger = logger

            logger.info(kasa_device)
            return kasa_device
        else:
            # Raise an error if the connection failed
            raise TpLinkKasaDeviceException("Could not connect to Kasa device at '{}".format(ip))

    async def do_action(self, command: str = 'status', children=None):
        # Create an empty list for child devices, if no list was provided
        if children is None:
            children = []
        else:
            # Sort the child list
            children.sort()

        # Get the current device
        current_device = self.iot_device
        self._logger.debug("Current Device: {}".format(current_device))

        # Start a list of devices to perform the action upon
        devices_to_action = []

        # Check if the current device has children (a "Strip" or "StripSocket")
        if current_device.device_type in (current_device.device_type.Strip, current_device.device_type.StripSocket):
            # Check if a list of child devices was provided
            if len(children) > 0:
                # Include child devices as specific indexes
                for child in children:
                    try:
                        # Access the child device at the given index
                        devices_to_action.append(current_device.children[child])
                    except Exception as e:
                        self._logger.error("Error accessing child device at index {} - {}".format(child, e))
            else:
                # Include all children
                devices_to_action = current_device.children
        else:
            # If the device doesn't have children, target just the current device
            devices_to_action.append(current_device)

        # Determine the command to run
        self._logger.info("Command to run: {}".format(command))

        # Loop through the list of devices to action
        for device in devices_to_action:
            self._logger.debug("Running '{}' command on Device: {}".format(command, device.alias))

            # Create a string to track device state change
            state_change_string = ""

            if command == "on":
                try:
                    if device.is_off:
                        state_change_string = "=> changing state to ON"
                        await device.turn_on()
                    else:
                        state_change_string = "=> is already ON"
                except Exception as e:
                    self._logger.error("Error performing action on device '{}': {}".format(device.alias, e))
            elif command == "off":
                try:
                    if device.is_on:
                        state_change_string = "=> changing state to OFF"
                        await device.turn_off()
                    else:
                        state_change_string = "=> is already OFF"
                except Exception as e:
                    self._logger.error("Error performing action on device '{}': {}".format(device.alias, e))
            elif command == "hw-info":
                try:
                    device_hw_info = TpLinkKasaDeviceHardwareInfo(device.hw_info)

                    self._logger.debug("Device Hardware Info: {}".format(device_hw_info))

                    state_change_string = "\nHardware Info:\n{}".format(device_hw_info)

                    # Show device and hardware info status just once, and then break out of the loop
                    await self.show_device_state(current_device, None, state_change_string)
                    break
                except Exception as e:
                    self._logger.error("Error performing action on device '{}': {}".format(device.alias, e))
            elif command == "status":
                state_change_string = ""
            else:
                logger.critical('Unknown or unsupported command: {}'.format(command))

            # Show status for current device
            await self.show_device_state(current_device, device, state_change_string)

    async def show_device_state(self, current_device: iotdevice.Device, child: iotdevice.Device = None,
                                state_change_string: str = ""):
        if child is None:
            child_string = ""
            child_state_string = ""
        else:
            child_string = "Child:| {} |".format(child.alias)
            child_state_string = "State: {} ".format("ON" if child.is_on else "OFF")

        self._logger.info("Device: {} {} {} {}".format(
            current_device.alias, child_string, child_state_string, state_change_string))


# Methods
async def run_command(device_ip, command, children=None):
    if children is None:
        children = []

    # Access the smart device
    device = await TpLinkKasaDevice.connect(device_ip, logger)

    logger.debug("Running command: {}".format(command))

    # Perform command
    await device.do_action(command=command, children=children)


def config_logger(log_name_prefix, log_level, log_path):
    # Log path existence / creation
    Path(log_path).mkdir(parents=True, exist_ok=True)

    # Log filename
    log_file_name = '{}/{}.log'.format(log_path, log_name_prefix)

    # Get logger
    my_logger = logging.getLogger(loggerName)

    # Set lowest allowed logger severity
    logger.setLevel(logging.DEBUG)

    # Console output handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s: %(message)s'))
    logger.addHandler(console_handler)

    # Log file output handler
    file_handler = logging.FileHandler(log_file_name)
    file_handler.setLevel(log_level)
    file_handler.encoding = 'utf-8'
    file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(lineno)d: %(message)s'))
    logger.addHandler(file_handler)

    # Return configured logger
    return my_logger


# Main function
async def main():
    # Configure logging
    logger = config_logger(Path(parser.prog).stem, logLevel, logPath)

    # Check for valid command
    command = args.command

    # Get command timeout
    command_timeout = args.timeout

    #  if command in valid_commands:
    if command in command_options:
        # Check for valid IP Address from CMD Args
        if re.match(
                r"(?:\b(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\b)\Z",
                args.ip):
            # Successful match at the start of the string
            device_ip = args.ip
        else:
            # IP match attempt failed
            logger.critical('Invalid IP Address: {}'.format(args.ip))
            exit()

        if re.match(r"^all|([0-9](,[0-9])*)$", args.children):
            if re.match(r"^all$", args.children):
                children = []
            else:
                children = ",".join(args.children)
                children = list(map(int, args.children.split(",")))
        else:
            children = []

        # Try to run command
        try:
            # Set a timeout
            async with asyncio.timeout(command_timeout):
                # Attempt to run the command
                await run_command(device_ip, command, children)
        except asyncio.TimeoutError as te:
            logger.critical('Error: Command "{}" timed out for device at {} | {}'.format(
                command,
                device_ip,
                te))
        except Exception as e:
            logger.critical('Error: {}'.format(e))
    else:
        logger.critical('Invalid command: {}'.format(command))
        exit()


# Initiate main
if __name__ == "__main__":
    asyncio.run(main())
else:
    help()
