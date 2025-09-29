# Import libraries
#from xmlrpc.client import Boolean
from datetime import datetime  # datetime library
from typing import List
import kasa.iot
from kasa.iot import iotdevice
import asyncio  # async io
import platform  # platform
import argparse  # argument parsing
import re  # regex
import json  # JSON
import logging  # Logging
from pathlib import Path  # Path functions

# Set platform policy
if platform.system() == 'Windows':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Set a default command response timeout (in seconds)
command_timeout_default = 3

# List of valid device command options
command_options = ['on', 'off', 'status']

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


# wrapper class for TP-Link Kasa Smart Device
class TpLinkKasaDevice:
    def __init__(self, ip: str, logger: logging.Logger = None):
        self.ip = ip
        self.iot_device = None
        self.type = None
        self.name = ''
        self.children = []
        self._logger = logger

    def __str__(self):
        return 'IP: {} | Name: {} | Device Type: {}'.format(
                self.ip, self.name, self.type)

    @staticmethod
    async def connect(ip: str, logger: logging.Logger = None):
        iot_device = await iotdevice.Device.connect(host=ip)

        if iot_device:
            kasa_device = TpLinkKasaDevice(ip)
            kasa_device.iot_device = iot_device
            kasa_device.type = iot_device.device_type
            kasa_device.name = iot_device.alias
            kasa_device.children = iot_device.children
            kasa_device._logger = logger

            logger.info(kasa_device)
            return kasa_device
        else:
            raise TpLinkKasaDeviceException("Could not connect to Kasa device at '{}".format(ip))

    async def turn_on(self, children=None):
        if children is None:
            children = []

        self._logger.debug("Getting device: {}".format(self.iot_device))
        current_device = self.iot_device

        self._logger.debug("Checking device type...")
        if self.type in (current_device.device_type.Strip, current_device.device_type.StripSocket):
            if not len(children) > 0:
                for i in range(len(current_device.children)):
                    children.append(i)

            self._logger.info("Device: {} - Turning on child devices".format(current_device.alias))
            for child in children:
                try:
                    current_child = current_device.children[child]

                    state_change_string = "=> is already ON"

                    if current_child.is_off:
                        await current_child.turn_on()

                        state_change_string = "=> changing state to ON"

                    self._logger.info("Device: {} | Child: {} | State: {} {}".format(
                            self.name, current_child.alias, "ON" if current_child.is_on else "OFF", state_change_string))
                except Exception as e:
                    self._logger.error("Error accessing child device: {}".format(e))
        else:
            state_change_string = "=> is already ON"

            if current_device.is_off:
                await current_device.turn_on()

                state_change_string = "=> changing state to ON"

            self._logger.info("Device: {} | State: {} {}".format(
                    self.name, "ON" if current_device.is_on else "OFF", state_change_string))

    async def turn_off(self, children=None):
        if children is None:
            children = []

        self._logger.debug("Getting device: {}".format(self.iot_device))
        current_device = self.iot_device

        self._logger.debug("Checking device type...")
        if self.type in (current_device.device_type.Strip, current_device.device_type.StripSocket):
            if not len(children) > 0:
                for i in range(len(current_device.children)):
                    children.append(i)

            self._logger.info("Device: {} - Turning off child devices".format(current_device.alias))
            for child in children:
                try:
                    current_child = current_device.children[child]

                    state_change_string = "=> is already OFF"

                    if current_child.is_on:
                        await current_child.turn_off()

                        state_change_string = "=> changed state to OFF"

                    self._logger.info("Device: {} | Child: {} | State: {} {}".format(
                        self.name, current_child.alias, "ON" if current_child.is_on else "OFF", state_change_string))
                except Exception as e:
                    self._logger.error("Error accessing child device: {}".format(e))
        else:
            state_change_string = "=> is already OFF"

            if current_device.is_on:
                await current_device.turn_off()

                state_change_string = "=> changed state to OFF"

            self._logger.info("Device: {} | State: {} {}".format(
                self.name, "ON" if current_device.is_on else "OFF", state_change_string))

    async def status(self, children=None):
        if children is None:
            children = []

        self._logger.debug("Getting device: {}".format(self.iot_device))
        current_device = self.iot_device

        self._logger.debug("Checking device type...")
        if self.type in (current_device.device_type.Strip, current_device.device_type.StripSocket):
            if not len(children) > 0:
                for i in range(len(current_device.children)):
                    children.append(i)

            self._logger.info("Device: {} - Getting status for child devices".format(current_device.alias))
            for child in children:
                try:
                    current_child = current_device.children[child]

                    self._logger.info("Device: {} | Child: {} | State: {}".format(
                        self.name, current_child.alias, "OFF" if current_child.is_off else "ON"
                    ))
                except Exception as e:
                    self._logger.error("Error accessing child device at index {}: {}".format(child, e))
        else:
            self._logger.info("Device: {} | State: {}".format(
                self.name, "OFF" if current_device.is_off else "ON"
            ))


# Methods
async def run_command(device_ip, command, children=None):
    if children is None:
        children = []

    # Access the smart device
    device = await TpLinkKasaDevice.connect(device_ip, logger)

    logger.debug("Running command: {}".format(command))

    # Perform command action
    if command == "on":
        await device.turn_on(children)
        children = []
    elif command == "off":
        await device.turn_off(children)
        children = []
    elif command == "status":
        await device.status(children)
    else:
        logger.critical('Unknown or unsupported command: {}'.format(command))


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
            # raise Exception('Command "{}" timed out for device at {}'.format(command, device_ip))
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
