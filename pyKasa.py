# Import libraries
#from xmlrpc.client import Boolean
from datetime import datetime  # datetime library
#import kasa  # kasa library
#import kasa.iot # kasa IOT library -- for devices that support non-authenticated access
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
command_options = ['on', 'off', 'toggle', 'status']

# CMD Line Parser
parser = argparse.ArgumentParser(description='Control a TP-Link Kasa Smart Device.')
parser.add_argument('--ip', help='The IP address of the device', required=True)
parser.add_argument('--child', type=int,
                    help='Zero-based index of child device to target (for devices like power strips)',
                    default=-1)
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


# Functions
async def runCommand(device_ip, command):
    # Access the smart device
    # device = await kasa.Discover.discover_single(device_ip)
    # device = await kasa.iot.iotdevice.Device.connect(host=device_ip)
    device = await iotdevice.Device.connect(host=device_ip)

    # Check if a device was found
    if device:
        # Show device details
        logger.info('IP: {} | Device Type: {} | Name: {}'.format(device_ip, device.device_type, device.alias))

        # Verbose Details
        logger.debug('Detailed info:')
        logger.debug(json.dumps(device.hw_info, indent=2))

        # Set the initial target device to run a command on
        target_device = device
        target_device_name = device.alias

        # Create a dictionary to store all command target devices
        logger.debug('Creating target device dictionary')
        target_devices = {}

        # Add initial target device to command target dictionary
        logger.debug('Creating first target device entry from parent device')
        target_devices[0] = {target_device_name: target_device}

        # Check if device has children
        if ((device.device_type.Strip) or (device.device_type.StripSocket)):
            logger.debug('Target device has child devices')
            logger.debug('Number of child devices: {}'.format(len(device.children)))
            logger.debug('Children: {}'.format(device.children))

            # Check if a child device was specified, and that is it a valid child
            # if ((args.child >= 0) and (len(device.children) > args.child)):
            if ((args.child >= 0) and (len(device.children) > args.child)):
                # If so, get the child index
                child_index = args.child
                logger.info('Child device -- Index: {} | Name: {}'.format(child_index,
                                                                           device.children[child_index].alias))

                # Set the target device
                target_device = device.children[child_index]
                target_device_name = '{} => {}'.format(device.alias, target_device.alias)

                logger.info('Setting child device {} as only target device'.format(child_index))
                target_devices[0] = {target_device_name: target_device}
            else:
                # Target all children
                logger.info('No child device specified. Targeting all child devices.')

                i = 0  # iterator for children
                for child in device.children:
                    target_device = child
                    target_device_name = '{} => {}'.format(device.alias, target_device.alias)

                    logger.info(
                        'Added target -- Device: {} | Child Index: {}'.format(target_device_name, i))
                    target_devices[i] = {target_device_name: target_device}
                    i = i + 1

        # Run command on target device(s)
        logger.info('Command: {} | Number of Devices: {}'.format(command, len(target_devices)))

        for index, target in target_devices.items():
            # Check for valid command
            for target_name, target_item in target.items():
                logger.info('Performing "{}" action for Device: {}'.format(command, target_name))

                # Perform command action
                if command == "on":
                    await turnOnDevice(target_item, target_name)
                elif command == "off":
                    await turnOffDevice(target_item, target_name)
                elif command == "toggle":
                    await toggleDevice(target_item, target_name)
                elif command == "status":
                    await showDeviceState(target_item, target_name)
                else:
                    logger.critical('Unknown or unsupported command: {}'.format(command))

    else:
        # No device found
        logger.critical('No smart device found at {}'.format(args.ip))
        exit()


async def turnOffDevice(device, device_name):
    # Check if device is currently on
    if device.is_on:
        # Turn off device
        logger.info('Turning off device: {}'.format(device_name))
        await device.turn_off()
    else:
        # Device is already off
        logger.info('Device "{}" is already off'.format(device_name))


async def turnOnDevice(device, device_name):
    # Check if device is on
    if device.is_on:
        # Device is already on
        logger.info('Device "{}" is already on'.format(device_name))
    else:
        # Turn on device
        logger.info('Turning on device: {}'.format(device_name))
        await device.turn_on()


async def toggleDevice(device, device_name):
    # Check if device is currently on
    if device.is_on:
        # Turn off device
        logger.info('Device: {} | Power State: ON -- Changing state to: OFF'.format(device_name))
        await turnOffDevice(device, device_name)
    else:
        # Turn on device
        logger.info('Device: {} | Power State: OFF -- Changing state to: ON'.format(device_name))
        await turnOnDevice(device, device_name)


async def getDeviceState(device):
    # Set a default state of "OFF"
    device_state = "OFF"

    # Check if device is on
    if device.is_on:
        device_state = "ON"

    return device_state


async def showDeviceState(device, device_name):
    # Get device state
    device_state = await getDeviceState(device)

    logger.info('Device: {} | Power State: {}'.format(device_name, device_state))


def printDebug(message, debug_mode):
    # Print message only if debug mode is enabled
    if debug_mode:
        print('|| -- DEBUG -- || {}'.format(message)) if (len(message) > 0) else print('')


def configLogger(logNamePrefix, logLevel, logPath):
    # Log path existence / creation
    Path(logPath).mkdir(parents=True, exist_ok=True)

    # Log filename
    logFileName = '{}/{}.log'.format(logPath, logNamePrefix)

    # Get logger
    myLogger = logging.getLogger(loggerName)

    # Set lowest allowed logger severity
    logger.setLevel(logging.DEBUG)

    # Console output handler
    consoleHandler = logging.StreamHandler()
    consoleHandler.setLevel(logLevel)
    consoleHandler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s: %(message)s'))
    logger.addHandler(consoleHandler)

    # Log file output handler
    fileHandler = logging.FileHandler(logFileName)
    fileHandler.setLevel(logLevel)
    fileHandler.encoding = 'utf-8'
    fileHandler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)s | %(lineno)d: %(message)s'))
    logger.addHandler(fileHandler)

    # Return configured logger
    return myLogger


# Main function
async def main():
    # Configure logging
    logger = configLogger(Path(parser.prog).stem, logLevel, logPath)

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

        # Try to run command
        try:
            # Set a timeout
            async with asyncio.timeout(command_timeout):
                # Attempt to run the command
                await runCommand(device_ip, command)
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
