#!/usr/bin/python
# vim:ts=4 sts=4 sw=4 expandtab

"""apple.py

Manages and launches iOS applications on device.

This is primarily intended to be used to run automated smoke tests of iOS
applications on non-jailbroken iOS devices.

See "apple.py -h" for usage.

A typical automated test might execute something like follow, to uninstall any
old versions of the app (-u), install the new one (-m), mount the developer
disk image (-m), run the app (-r), and pass the arguments "--smokeTest" to the
app (-a).
    apple.py -b build/Example.app -u -i -m -r -a --smokeTest

This will display all output from the app to standard out as it is running and
exit with the application's exit code.
"""

__author__ = 'Cory McWilliams <cory@unprompted.com>'
__version__ = "1.0.0"

__license__ = """
Copyright (c) 2013 Cory McWilliams <cory@unprompted.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

__credits__ = """
Made possible by:
1. fruitstrap from Greg Hughes: <https://github.com/ghughes/fruitstrap.git>
   Why didn't Apple just write this and save us all time?
2. idevice-app-runner for demonstrating that you don't need gdb to talk to
   debugserver: <https://github.com/crackleware/idevice-app-runner.git>
3. libimobiledevice for demonstrating how to make penguins talk to fruits:
   <http://www.libimobiledevice.org/>
"""

import argparse
import binascii
import ctypes
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import struct
import time

# CoreFoundation.framework

if sys.platform == 'win32':
    CoreFoundation = ctypes.CDLL(os.path.join(os.environ['CommonProgramFiles'], 'Apple', 'Mobile Device Support','CoreFoundation.dll'))
else:
    CoreFoundation = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')

CFShow = CoreFoundation.CFShow
CFShow.argtypes = [ctypes.c_void_p]
CFShow.restype = None

CFGetTypeID = CoreFoundation.CFGetTypeID
CFGetTypeID.argtypes = [ctypes.c_void_p]
CFGetTypeID.restype = ctypes.c_ulong

CFStringRef = ctypes.c_void_p

CFStringGetTypeID = CoreFoundation.CFStringGetTypeID
CFStringGetTypeID.argtypes = []
CFStringGetTypeID.restype = ctypes.c_ulong

CFDictionaryGetTypeID = CoreFoundation.CFDictionaryGetTypeID
CFDictionaryGetTypeID.argtypes = []
CFDictionaryGetTypeID.restype = ctypes.c_ulong

CFStringGetLength = CoreFoundation.CFStringGetLength
CFStringGetLength.argtypes = [CFStringRef]
CFStringGetLength.restype = ctypes.c_ulong

CFCopyDescription = CoreFoundation.CFCopyDescription
CFCopyDescription.argtypes = [ctypes.c_void_p]
CFCopyDescription.restype = CFStringRef

CFNumberGetValue = CoreFoundation.CFNumberGetValue
CFNumberGetValue.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p]
CFNumberGetValue.restype = ctypes.c_bool

kCFNumberSInt32Type = 3

CFRunLoopRun = CoreFoundation.CFRunLoopRun
CFRunLoopRun.argtypes = []
CFRunLoopRun.restype = None

CFRunLoopStop = CoreFoundation.CFRunLoopStop
CFRunLoopStop.argtypes = [ctypes.c_void_p]
CFRunLoopStop.restype = None

CFRunLoopGetCurrent = CoreFoundation.CFRunLoopGetCurrent
CFRunLoopGetCurrent.argtype = []
CFRunLoopGetCurrent.restype = ctypes.c_void_p

cf_run_loop_timer_callback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)

CFRunLoopTimerCreate = CoreFoundation.CFRunLoopTimerCreate
CFRunLoopTimerCreate.argtypes = [ctypes.c_void_p, ctypes.c_double, ctypes.c_double, ctypes.c_uint, ctypes.c_uint, cf_run_loop_timer_callback, ctypes.c_void_p]
CFRunLoopTimerCreate.restype = ctypes.c_void_p

kCFRunLoopCommonModes = CFStringRef.in_dll(CoreFoundation, 'kCFRunLoopCommonModes')

CFAbsoluteTimeGetCurrent = CoreFoundation.CFAbsoluteTimeGetCurrent
CFAbsoluteTimeGetCurrent.argtypes = []
CFAbsoluteTimeGetCurrent.restype = ctypes.c_double

CFRunLoopAddTimer = CoreFoundation.CFRunLoopAddTimer
CFRunLoopAddTimer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, CFStringRef]
CFRunLoopAddTimer.restype = None

CFRunLoopRemoveTimer = CoreFoundation.CFRunLoopRemoveTimer
CFRunLoopRemoveTimer.argtypes = [ctypes.c_void_p, ctypes.c_void_p, CFStringRef]
CFRunLoopRemoveTimer.restype = None

CFDictionaryRef = ctypes.c_void_p

class CFDictionaryKeyCallBacks(ctypes.Structure):
    _fields_ = [
        ('version', ctypes.c_uint),
        ('retain', ctypes.c_void_p),
        ('release', ctypes.c_void_p),
        ('copyDescription', ctypes.c_void_p),
        ('equal', ctypes.c_void_p),
        ('hash', ctypes.c_void_p),
    ]

class CFDictionaryValueCallBacks(ctypes.Structure):
    _fields_ = [
        ('version', ctypes.c_uint),
        ('retain', ctypes.c_void_p),
        ('release', ctypes.c_void_p),
        ('copyDescription', ctypes.c_void_p),
        ('equal', ctypes.c_void_p),
    ]

CFDictionaryCreate = CoreFoundation.CFDictionaryCreate
CFDictionaryCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p), ctypes.c_int, ctypes.POINTER(CFDictionaryKeyCallBacks), ctypes.POINTER(CFDictionaryValueCallBacks)]
CFDictionaryCreate.restype = CFDictionaryRef

CFDictionaryGetValue = CoreFoundation.CFDictionaryGetValue
CFDictionaryGetValue.argtypes = [CFDictionaryRef, CFStringRef]
CFDictionaryGetValue.restype = ctypes.c_void_p

CFDictionaryGetCount = CoreFoundation.CFDictionaryGetCount
CFDictionaryGetCount.argtypes = [CFDictionaryRef]
CFDictionaryGetCount.restype = ctypes.c_int

CFDictionaryGetKeysAndValues = CoreFoundation.CFDictionaryGetKeysAndValues
CFDictionaryGetKeysAndValues.argtypes = [CFDictionaryRef, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_void_p)]
CFDictionaryGetKeysAndValues.restype = None

kCFTypeDictionaryKeyCallBacks = CFDictionaryKeyCallBacks.in_dll(CoreFoundation, 'kCFTypeDictionaryKeyCallBacks')
kCFTypeDictionaryValueCallBacks = CFDictionaryValueCallBacks.in_dll(CoreFoundation, 'kCFTypeDictionaryValueCallBacks')

CFDataRef = ctypes.c_void_p
CFDataCreate = CoreFoundation.CFDataCreate
CFDataCreate.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
CFDataCreate.restype = ctypes.c_void_p

CFStringCreateWithCString = CoreFoundation.CFStringCreateWithCString
CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint]
CFStringCreateWithCString.restype = CFStringRef

def CFStr(value):
    return CFStringCreateWithCString(None, value.encode('utf-8'), kCFStringEncodingUTF8)

CFStringGetCStringPtr = CoreFoundation.CFStringGetCStringPtr
CFStringGetCStringPtr.argtypes = [CFStringRef, ctypes.c_uint]
CFStringGetCStringPtr.restype = ctypes.c_char_p

CFStringGetCString = CoreFoundation.CFStringGetCString
CFStringGetCString.argtypes = [CFStringRef, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint]
CFStringGetCString.restype = ctypes.c_bool

kCFStringEncodingUTF8 = 0x08000100

def CFStringGetStr(cfstr):
    result = None
    if cfstr:
        result = CFStringGetCStringPtr(cfstr, kCFStringEncodingUTF8)
        if not result:
            length = CFStringGetLength(cfstr) * 2 + 1
            stringBuffer = ctypes.create_string_buffer(length)
            CFStringGetCString(cfstr, stringBuffer, length, kCFStringEncodingUTF8)
            result = stringBuffer.value
    return result.decode("utf8")

def CFDictionaryToDict(dictionary):
    count = CFDictionaryGetCount(dictionary)
    keys = (ctypes.c_void_p * count)()
    values = (ctypes.c_void_p * count)()
    CFDictionaryGetKeysAndValues(dictionary, keys, values)
    keys = [CFToPython(key) for key in keys]
    values = [CFToPython(value) for value in values]
    return dict(list(zip(keys, values)))

def CFToPython(dataRef):
    typeId = CFGetTypeID(dataRef)
    if typeId == CFStringGetTypeID():
        return CFStringGetStr(dataRef)
    elif typeId == CFDictionaryGetTypeID():
        return CFDictionaryToDict(dataRef)
    else:
        description = CFCopyDescription(dataRef)
        return CFStringGetStr(description)

# MobileDevice.Framework

if sys.platform == 'win32':
    MobileDevice = ctypes.CDLL(os.path.join(os.environ['CommonProgramFiles'], 'Apple', 'Mobile Device Support','MobileDevice.dll'))
else:
    MobileDevice = ctypes.CDLL('/System/Library/PrivateFrameworks/MobileDevice.framework/MobileDevice')

AMDSetLogLevel = MobileDevice.AMDSetLogLevel
AMDSetLogLevel.argtypes = [ctypes.c_int]
AMDSetLogLevel.restype = None

AMDSetLogLevel(5)

am_device_p = ctypes.c_void_p

class am_device_notification(ctypes.Structure):
    pass

class am_device_notification_callback_info(ctypes.Structure):
    _fields_ = [
        ('dev', am_device_p),
        ('msg', ctypes.c_uint),
        ('subscription', ctypes.POINTER(am_device_notification)),
    ]

am_device_notification_callback = ctypes.CFUNCTYPE(None, ctypes.POINTER(am_device_notification_callback_info), ctypes.c_int)

am_device_notification._fields_ = [
    ('unknown0', ctypes.c_uint),
    ('unknown1', ctypes.c_uint),
    ('unknown2', ctypes.c_uint),
    ('callback', ctypes.c_void_p),
    ('cookie', ctypes.c_uint),
]

am_device_notification_p = ctypes.POINTER(am_device_notification)

AMDeviceNotificationSubscribe = MobileDevice.AMDeviceNotificationSubscribe
AMDeviceNotificationSubscribe.argtypes = [am_device_notification_callback, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p)]
AMDeviceNotificationSubscribe.restype = ctypes.c_uint

AMDeviceNotificationUnsubscribe = MobileDevice.AMDeviceNotificationUnsubscribe
AMDeviceNotificationUnsubscribe.argtypes = [ctypes.c_void_p]
AMDeviceNotificationUnsubscribe.restype = ctypes.c_uint

ADNCI_MSG_CONNECTED = 1
ADNCI_MSG_DISCONNECTED = 2
ADNCI_MSG_UNKNOWN = 3

AMDeviceCopyValue = MobileDevice.AMDeviceCopyValue
AMDeviceCopyValue.argtypes = [am_device_p, CFStringRef, CFStringRef]
AMDeviceCopyValue.restype = CFStringRef

AMDeviceGetConnectionID = MobileDevice.AMDeviceGetConnectionID
AMDeviceGetConnectionID.argtypes = [am_device_p]
AMDeviceGetConnectionID.restype = ctypes.c_uint

AMDeviceCopyDeviceIdentifier = MobileDevice.AMDeviceCopyDeviceIdentifier
AMDeviceCopyDeviceIdentifier.argtypes = [am_device_p]
AMDeviceCopyDeviceIdentifier.restype = CFStringRef

AMDeviceConnect = MobileDevice.AMDeviceConnect
AMDeviceConnect.argtypes = [am_device_p]
AMDeviceConnect.restype = ctypes.c_uint

AMDevicePair = MobileDevice.AMDevicePair
AMDevicePair.argtypes = [am_device_p]
AMDevicePair.restype = ctypes.c_uint

AMDeviceIsPaired = MobileDevice.AMDeviceIsPaired
AMDeviceIsPaired.argtypes = [am_device_p]
AMDeviceIsPaired.restype = ctypes.c_uint

AMDeviceValidatePairing = MobileDevice.AMDeviceValidatePairing
AMDeviceValidatePairing.argtypes = [am_device_p]
AMDeviceValidatePairing.restype = ctypes.c_uint

AMDeviceStartSession = MobileDevice.AMDeviceStartSession
AMDeviceStartSession.argtypes = [am_device_p]
AMDeviceStartSession.restype = ctypes.c_uint

AMDeviceStopSession = MobileDevice.AMDeviceStopSession
AMDeviceStopSession.argtypes = [am_device_p]
AMDeviceStopSession.restype = ctypes.c_uint

AMDeviceDisconnect = MobileDevice.AMDeviceDisconnect
AMDeviceDisconnect.argtypes = [am_device_p]
AMDeviceDisconnect.restype = ctypes.c_uint

am_device_mount_image_callback = ctypes.CFUNCTYPE(ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p)

try:
    AMDeviceMountImage = MobileDevice.AMDeviceMountImage
    AMDeviceMountImage.argtypes = [am_device_p, CFStringRef, CFDictionaryRef, am_device_mount_image_callback, ctypes.c_void_p]
    AMDeviceMountImage.restype = ctypes.c_uint
except AttributeError:
    # AMDeviceMountImage is missing on win32.
    AMDeviceMountImage = None

AMDeviceStartService = MobileDevice.AMDeviceStartService
AMDeviceStartService.argtypes = [am_device_p, CFStringRef, ctypes.POINTER(ctypes.c_int), ctypes.c_void_p]
AMDeviceStartService.restype = ctypes.c_uint

AMDeviceStartHouseArrestService = MobileDevice.AMDeviceStartHouseArrestService
AMDeviceStartHouseArrestService.argtypes = [am_device_p, CFStringRef, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_void_p]
AMDeviceStartHouseArrestService.restype = ctypes.c_uint

AMDeviceSecureStartService = MobileDevice.AMDeviceSecureStartService
AMDeviceSecureStartService.argtypes = [am_device_p, CFStringRef, CFDictionaryRef, ctypes.POINTER(ctypes.c_void_p)]
AMDeviceSecureStartService.restype = ctypes.c_uint

AMDServiceConnectionGetSocket = MobileDevice.AMDServiceConnectionGetSocket
AMDServiceConnectionGetSocket.argtypes = [ctypes.c_void_p]
AMDServiceConnectionGetSocket.restype = ctypes.c_uint

AMDServiceConnectionInvalidate = MobileDevice.AMDServiceConnectionInvalidate
AMDServiceConnectionInvalidate.argtypes = [ctypes.c_void_p]
AMDServiceConnectionInvalidate.restype = None

AMDServiceConnectionSend = MobileDevice.AMDServiceConnectionSend
AMDServiceConnectionSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
AMDServiceConnectionSend.restype = ctypes.c_int32

AMDServiceConnectionReceive = MobileDevice.AMDServiceConnectionReceive
AMDServiceConnectionSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32]
AMDServiceConnectionSend.restype = ctypes.c_int32

am_device_install_application_callback = ctypes.CFUNCTYPE(ctypes.c_uint, CFDictionaryRef, ctypes.c_void_p)

AMDeviceTransferApplication = MobileDevice.AMDeviceTransferApplication
AMDeviceTransferApplication.argtypes = [ctypes.c_int, CFStringRef, CFDictionaryRef, am_device_install_application_callback, ctypes.c_void_p]
AMDeviceTransferApplication.restype = ctypes.c_uint

AMDeviceInstallApplication = MobileDevice.AMDeviceInstallApplication
AMDeviceInstallApplication.argtypes = [ctypes.c_int, CFStringRef, CFDictionaryRef, am_device_install_application_callback, ctypes.c_void_p]
AMDeviceInstallApplication.restype = ctypes.c_uint

AMDeviceUninstallApplication = MobileDevice.AMDeviceUninstallApplication
AMDeviceUninstallApplication.argtypes = [ctypes.c_int, CFStringRef, CFDictionaryRef, am_device_install_application_callback, ctypes.c_void_p]
AMDeviceUninstallApplication.restype = ctypes.c_uint

AMDeviceLookupApplications = MobileDevice.AMDeviceLookupApplications
AMDeviceLookupApplications.argtypes = [am_device_p, ctypes.c_uint, ctypes.POINTER(CFDictionaryRef)]
AMDeviceLookupApplications.restype = ctypes.c_uint

# AFC

AFCConnectionRef = ctypes.c_void_p
AFCFileRef = ctypes.c_uint64

AFCConnectionOpen = MobileDevice.AFCConnectionOpen
AFCConnectionOpen.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.POINTER(AFCConnectionRef)]
AFCConnectionOpen.restype = ctypes.c_uint

AFCConnectionClose = MobileDevice.AFCConnectionClose
AFCConnectionClose.argtypes = [AFCConnectionRef]
AFCConnectionClose.restype = ctypes.c_uint

AFCFileRefOpen = MobileDevice.AFCFileRefOpen
AFCFileRefOpen.argtypes = [AFCConnectionRef, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(AFCFileRef)]
AFCFileRefOpen.restype = ctypes.c_uint

AFCFileRefRead = MobileDevice.AFCFileRefRead
AFCFileRefRead.argtypes = [AFCConnectionRef, AFCFileRef, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
AFCFileRefRead.restype = ctypes.c_uint

AFCFileRefWrite = MobileDevice.AFCFileRefWrite
AFCFileRefWrite.argtypes = [AFCConnectionRef, AFCFileRef, ctypes.c_void_p, ctypes.c_uint]
AFCFileRefWrite.restype = ctypes.c_uint

AFCFileRefClose = MobileDevice.AFCFileRefClose
AFCFileRefClose.argtypes = [AFCConnectionRef, AFCFileRef]
AFCFileRefClose.restype = ctypes.c_uint

AFCDirectoryCreate = MobileDevice.AFCDirectoryCreate
AFCDirectoryCreate.argtypes = [AFCConnectionRef, ctypes.c_char_p]
AFCDirectoryCreate.restype = ctypes.c_uint

AFCDirectoryRef = ctypes.c_void_p

AFCDirectoryOpen = MobileDevice.AFCDirectoryOpen
AFCDirectoryOpen.argtypes = [AFCConnectionRef, ctypes.c_char_p, ctypes.POINTER(AFCDirectoryRef)]
AFCDirectoryOpen.restype = ctypes.c_uint

AFCDirectoryRead = MobileDevice.AFCDirectoryRead
AFCDirectoryRead.argtypes = [AFCConnectionRef, AFCDirectoryRef, ctypes.POINTER(ctypes.c_char_p)]
AFCDirectoryRead.restype = ctypes.c_uint

AFCDirectoryClose = MobileDevice.AFCDirectoryClose
AFCDirectoryClose.argtypes = [AFCConnectionRef, AFCDirectoryRef]
AFCDirectoryClose.restype = ctypes.c_uint

def _get_mobile_device_error(error_code):
    # Sourced this list from https://github.com/ios-control/ios-deploy
    _error_code_to_message = {
        0x00000000: "kAMDSuccess",
        0xe8000001: "kAMDUndefinedError",
        0xe8000002: "kAMDBadHeaderError",
        0xe8000003: "kAMDNoResourcesError",
        0xe8000004: "kAMDReadError",
        0xe8000005: "kAMDWriteError",
        0xe8000006: "kAMDUnknownPacketError",
        0xe8000007: "kAMDInvalidArgumentError",
        0xe8000008: "kAMDNotFoundError",
        0xe8000009: "kAMDIsDirectoryError",
        0xe800000a: "kAMDPermissionError",
        0xe800000b: "kAMDNotConnectedError",
        0xe800000c: "kAMDTimeOutError",
        0xe800000d: "kAMDOverrunError",
        0xe800000e: "kAMDEOFError",
        0xe800000f: "kAMDUnsupportedError",
        0xe8000010: "kAMDFileExistsError",
        0xe8000011: "kAMDBusyError",
        0xe8000012: "kAMDCryptoError",
        0xe8000013: "kAMDInvalidResponseError",
        0xe8000014: "kAMDMissingKeyError",
        0xe8000015: "kAMDMissingValueError",
        0xe8000016: "kAMDGetProhibitedError",
        0xe8000017: "kAMDSetProhibitedError",
        0xe8000018: "kAMDRemoveProhibitedError",
        0xe8000019: "kAMDImmutableValueError",
        0xe800001a: "kAMDPasswordProtectedError",
        0xe800001b: "kAMDMissingHostIDError",
        0xe800001c: "kAMDInvalidHostIDError",
        0xe800001d: "kAMDSessionActiveError",
        0xe800001e: "kAMDSessionInactiveError",
        0xe800001f: "kAMDMissingSessionIDError",
        0xe8000020: "kAMDInvalidSessionIDError",
        0xe8000021: "kAMDMissingServiceError",
        0xe8000022: "kAMDInvalidServiceError",
        0xe8000023: "kAMDInvalidCheckinError",
        0xe8000024: "kAMDCheckinTimeoutError",
        0xe8000025: "kAMDMissingPairRecordError",
        0xe8000026: "kAMDInvalidActivationRecordError",
        0xe8000027: "kAMDMissingActivationRecordError",
        0xe8000028: "kAMDWrongDroidError",
        0xe8000029: "kAMDSUVerificationError",
        0xe800002a: "kAMDSUPatchError",
        0xe800002b: "kAMDSUFirmwareError",
        0xe800002c: "kAMDProvisioningProfileNotValid",
        0xe800002d: "kAMDSendMessageError",
        0xe800002e: "kAMDReceiveMessageError",
        0xe800002f: "kAMDMissingOptionsError",
        0xe8000030: "kAMDMissingImageTypeError",
        0xe8000031: "kAMDDigestFailedError",
        0xe8000032: "kAMDStartServiceError",
        0xe8000033: "kAMDInvalidDiskImageError",
        0xe8000034: "kAMDMissingDigestError",
        0xe8000035: "kAMDMuxError",
        0xe8000036: "kAMDApplicationAlreadyInstalledError",
        0xe8000037: "kAMDApplicationMoveFailedError",
        0xe8000038: "kAMDApplicationSINFCaptureFailedError",
        0xe8000039: "kAMDApplicationSandboxFailedError",
        0xe800003a: "kAMDApplicationVerificationFailedError",
        0xe800003b: "kAMDArchiveDestructionFailedError",
        0xe800003c: "kAMDBundleVerificationFailedError",
        0xe800003d: "kAMDCarrierBundleCopyFailedError",
        0xe800003e: "kAMDCarrierBundleDirectoryCreationFailedError",
        0xe800003f: "kAMDCarrierBundleMissingSupportedSIMsError",
        0xe8000040: "kAMDCommCenterNotificationFailedError",
        0xe8000041: "kAMDContainerCreationFailedError",
        0xe8000042: "kAMDContainerP0wnFailedError",
        0xe8000043: "kAMDContainerRemovalFailedError",
        0xe8000044: "kAMDEmbeddedProfileInstallFailedError",
        0xe8000045: "kAMDErrorError",
        0xe8000046: "kAMDExecutableTwiddleFailedError",
        0xe8000047: "kAMDExistenceCheckFailedError",
        0xe8000048: "kAMDInstallMapUpdateFailedError",
        0xe8000049: "kAMDManifestCaptureFailedError",
        0xe800004a: "kAMDMapGenerationFailedError",
        0xe800004b: "kAMDMissingBundleExecutableError",
        0xe800004c: "kAMDMissingBundleIdentifierError",
        0xe800004d: "kAMDMissingBundlePathError",
        0xe800004e: "kAMDMissingContainerError",
        0xe800004f: "kAMDNotificationFailedError",
        0xe8000050: "kAMDPackageExtractionFailedError",
        0xe8000051: "kAMDPackageInspectionFailedError",
        0xe8000052: "kAMDPackageMoveFailedError",
        0xe8000053: "kAMDPathConversionFailedError",
        0xe8000054: "kAMDRestoreContainerFailedError",
        0xe8000055: "kAMDSeatbeltProfileRemovalFailedError",
        0xe8000056: "kAMDStageCreationFailedError",
        0xe8000057: "kAMDSymlinkFailedError",
        0xe8000058: "kAMDiTunesArtworkCaptureFailedError",
        0xe8000059: "kAMDiTunesMetadataCaptureFailedError",
        0xe800005a: "kAMDAlreadyArchivedError",
        0xe800005b: "kAMDServiceLimitError",
        0xe800005c: "kAMDInvalidPairRecordError",
        0xe800005d: "kAMDServiceProhibitedError",
        0xe800005e: "kAMDCheckinSetupFailedError",
        0xe800005f: "kAMDCheckinConnectionFailedError",
        0xe8000060: "kAMDCheckinReceiveFailedError",
        0xe8000061: "kAMDCheckinResponseFailedError",
        0xe8000062: "kAMDCheckinSendFailedError",
        0xe8000063: "kAMDMuxCreateListenerError",
        0xe8000064: "kAMDMuxGetListenerError",
        0xe8000065: "kAMDMuxConnectError",
        0xe8000066: "kAMDUnknownCommandError",
        0xe8000067: "kAMDAPIInternalError",
        0xe8000068: "kAMDSavePairRecordFailedError",
        0xe8000069: "kAMDCheckinOutOfMemoryError",
        0xe800006a: "kAMDDeviceTooNewError",
        0xe800006b: "kAMDDeviceRefNoGood",
        0xe800006c: "kAMDCannotTranslateError",
        0xe800006d: "kAMDMobileImageMounterMissingImageSignature",
        0xe800006e: "kAMDMobileImageMounterResponseCreationFailed",
        0xe800006f: "kAMDMobileImageMounterMissingImageType",
        0xe8000070: "kAMDMobileImageMounterMissingImagePath",
        0xe8000071: "kAMDMobileImageMounterImageMapLoadFailed",
        0xe8000072: "kAMDMobileImageMounterAlreadyMounted",
        0xe8000073: "kAMDMobileImageMounterImageMoveFailed",
        0xe8000074: "kAMDMobileImageMounterMountPathMissing",
        0xe8000075: "kAMDMobileImageMounterMountPathNotEmpty",
        0xe8000076: "kAMDMobileImageMounterImageMountFailed",
        0xe8000077: "kAMDMobileImageMounterTrustCacheLoadFailed",
        0xe8000078: "kAMDMobileImageMounterDigestFailed",
        0xe8000079: "kAMDMobileImageMounterDigestCreationFailed",
        0xe800007a: "kAMDMobileImageMounterImageVerificationFailed",
        0xe800007b: "kAMDMobileImageMounterImageInfoCreationFailed",
        0xe800007c: "kAMDMobileImageMounterImageMapStoreFailed",
        0xe800007d: "kAMDBonjourSetupError",
        0xe800007e: "kAMDDeviceOSVersionTooLow",
        0xe800007f: "kAMDNoWifiSyncSupportError",
        0xe8000080: "kAMDDeviceFamilyNotSupported",
        0xe8000081: "kAMDEscrowLockedError",
        0xe8000082: "kAMDPairingProhibitedError",
        0xe8000083: "kAMDProhibitedBySupervision",
        0xe8000084: "kAMDDeviceDisconnectedError",
        0xe8000085: "kAMDTooBigError",
        0xe8000086: "kAMDPackagePatchFailedError",
        0xe8000087: "kAMDIncorrectArchitectureError",
        0xe8000088: "kAMDPluginCopyFailedError",
        0xe8000089: "kAMDBreadcrumbFailedError",
        0xe800008a: "kAMDBreadcrumbUnlockError",
        0xe800008b: "kAMDGeoJSONCaptureFailedError",
        0xe800008c: "kAMDNewsstandArtworkCaptureFailedError",
        0xe800008d: "kAMDMissingCommandError",
        0xe800008e: "kAMDNotEntitledError",
        0xe800008f: "kAMDMissingPackagePathError",
        0xe8000090: "kAMDMissingContainerPathError",
        0xe8000091: "kAMDMissingApplicationIdentifierError",
        0xe8000092: "kAMDMissingAttributeValueError",
        0xe8000093: "kAMDLookupFailedError",
        0xe8000094: "kAMDDictCreationFailedError",
        0xe8000095: "kAMDUserDeniedPairingError",
        0xe8000096: "kAMDPairingDialogResponsePendingError",
        0xe8000097: "kAMDInstallProhibitedError",
        0xe8000098: "kAMDUninstallProhibitedError",
        0xe8000099: "kAMDFMiPProtectedError",
        0xe800009a: "kAMDMCProtected",
        0xe800009b: "kAMDMCChallengeRequired",
        0xe800009c: "kAMDMissingBundleVersionError",
        0xe800009d: "kAMDAppBlacklistedError",
        0xe800009e: "This app contains an app extension with an illegal bundle identifier. App extension bundle identifiers must have a prefix consisting of their containing application's bundle identifier followed by a '.'.",
        0xe800009f: "If an app extension defines the XPCService key in its Info.plist, it must have a dictionary value.",
        0xe80000a0: "App extensions must define the NSExtension key with a dictionary value in their Info.plist.",
        0xe80000a1: "If an app extension defines the CFBundlePackageType key in its Info.plist, it must have the value \"XPC!\".",
        0xe80000a2: "App extensions must define either NSExtensionMainStoryboard or NSExtensionPrincipalClass keys in the NSExtension dictionary in their Info.plist.",
        0xe80000a3: "If an app extension defines the NSExtensionContextClass key in the NSExtension dictionary in its Info.plist, it must have a string value containing one or more characters.",
        0xe80000a4: "If an app extension defines the NSExtensionContextHostClass key in the NSExtension dictionary in its Info.plist, it must have a string value containing one or more characters.",
        0xe80000a5: "If an app extension defines the NSExtensionViewControllerHostClass key in the NSExtension dictionary in its Info.plist, it must have a string value containing one or more characters.",
        0xe80000a6: "This app contains an app extension that does not define the NSExtensionPointIdentifier key in its Info.plist. This key must have a reverse-DNS format string value.",
        0xe80000a7: "This app contains an app extension that does not define the NSExtensionPointIdentifier key in its Info.plist with a valid reverse-DNS format string value.",
        0xe80000a8: "If an app extension defines the NSExtensionAttributes key in the NSExtension dictionary in its Info.plist, it must have a dictionary value.",
        0xe80000a9: "If an app extension defines the NSExtensionPointName key in the NSExtensionAttributes dictionary in the NSExtension dictionary in its Info.plist, it must have a string value containing one or more characters.",
        0xe80000aa: "If an app extension defines the NSExtensionPointVersion key in the NSExtensionAttributes dictionary in the NSExtension dictionary in its Info.plist, it must have a string value containing one or more characters.",
        0xe80000ab: "This app or a bundle it contains does not define the CFBundleName key in its Info.plist with a string value containing one or more characters.",
        0xe80000ac: "This app or a bundle it contains does not define the CFBundleDisplayName key in its Info.plist with a string value containing one or more characters.",
        0xe80000ad: "This app or a bundle it contains defines the CFBundleShortVersionStringKey key in its Info.plist with a non-string value or a zero-length string value.",
        0xe80000ae: "This app or a bundle it contains defines the RunLoopType key in the XPCService dictionary in its Info.plist with a non-string value or a zero-length string value.",
        0xe80000af: "This app or a bundle it contains defines the ServiceType key in the XPCService dictionary in its Info.plist with a non-string value or a zero-length string value.",
        0xe80000b0: "This application or a bundle it contains has the same bundle identifier as this application or another bundle that it contains. Bundle identifiers must be unique.",
        0xe80000b1: "This app contains an app extension that specifies an extension point identifier that is not supported on this version of iOS for the value of the NSExtensionPointIdentifier key in its Info.plist.",
        0xe80000b2: "This app contains multiple app extensions that are file providers. Apps are only allowed to contain at most a single file provider app extension.",
        0xe80000b3: "kMobileHouseArrestMissingCommand",
        0xe80000b4: "kMobileHouseArrestUnknownCommand",
        0xe80000b5: "kMobileHouseArrestMissingIdentifier",
        0xe80000b6: "kMobileHouseArrestDictionaryFailed",
        0xe80000b7: "kMobileHouseArrestInstallationLookupFailed",
        0xe80000b8: "kMobileHouseArrestApplicationLookupFailed",
        0xe80000b9: "kMobileHouseArrestMissingContainer",
        # 0xe80000ba does not exist
        0xe80000bb: "kMobileHouseArrestPathConversionFailed",
        0xe80000bc: "kMobileHouseArrestPathMissing",
        0xe80000bd: "kMobileHouseArrestInvalidPath",
        0xe80000be: "kAMDMismatchedApplicationIdentifierEntitlementError",
        0xe80000bf: "kAMDInvalidSymlinkError",
        0xe80000c0: "kAMDNoSpaceError",
        0xe80000c1: "The WatchKit app extension must have, in its Info.plist's NSExtension dictionary's NSExtensionAttributes dictionary, the key WKAppBundleIdentifier with a value equal to the associated WatchKit app's bundle identifier.",
        0xe80000c2: "This app is not a valid AppleTV Stub App",
        0xe80000c3: "kAMDBundleiTunesMetadataVersionMismatchError",
        0xe80000c4: "kAMDInvalidiTunesMetadataPlistError",
        0xe80000c5: "kAMDMismatchedBundleIDSigningIdentifierError",
        0xe80000c6: "This app contains multiple WatchKit app extensions. Only a single WatchKit extension is allowed.",
        0xe80000c7: "A WatchKit app within this app is not a valid bundle.",
        0xe80000c8: "kAMDDeviceNotSupportedByThinningError",
        0xe80000c9: "The UISupportedDevices key in this app's Info.plist does not specify a valid set of supported devices.",
        0xe80000ca: "This app contains an app extension with an illegal bundle identifier. App extension bundle identifiers must have a prefix consisting of their containing application's bundle identifier followed by a '.', with no further '.' characters after the prefix.",
        0xe80000cb: "kAMDAppexBundleIDConflictWithOtherIdentifierError",
        0xe80000cc: "kAMDBundleIDConflictWithOtherIdentifierError",
        0xe80000cd: "This app contains multiple WatchKit 1.0 apps. Only a single WatchKit 1.0 app is allowed.",
        0xe80000ce: "This app contains multiple WatchKit 2.0 apps. Only a single WatchKit 2.0 app is allowed.",
        0xe80000cf: "The WatchKit app has an invalid stub executable.",
        0xe80000d0: "The WatchKit app has multiple app extensions. Only a single WatchKit extension is allowed in a WatchKit app, and only if this is a WatchKit 2.0 app.",
        0xe80000d1: "The WatchKit 2.0 app contains non-WatchKit app extensions. Only WatchKit app extensions are allowed in WatchKit apps.",
        0xe80000d2: "The WatchKit app has one or more embedded frameworks. Frameworks are only allowed in WatchKit app extensions in WatchKit 2.0 apps.",
        0xe80000d3: "This app contains a WatchKit 1.0 app with app extensions. This is not allowed.",
        0xe80000d4: "This app contains a WatchKit 2.0 app without an app extension. WatchKit 2.0 apps must contain a WatchKit app extension.",
        0xe80000d5: "The WatchKit app's Info.plist must have a WKCompanionAppBundleIdentifier key set to the bundle identifier of the companion app.",
        0xe80000d6: "The WatchKit app's Info.plist contains a non-string key.",
        0xe80000d7: "The WatchKit app's Info.plist contains a key that is not in the whitelist of allowed keys for a WatchKit app.",
        0xe80000d8: "The WatchKit 1.0 and a WatchKit 2.0 apps within this app must have have the same bundle identifier.",
        0xe80000d9: "This app contains a WatchKit app with an invalid bundle identifier. The bundle identifier of a WatchKit app must have a prefix consisting of the companion app's bundle identifier, followed by a '.'.",
        0xe80000da: "This app contains a WatchKit app where the UIDeviceFamily key in its Info.plist does not specify the value 4 to indicate that it's compatible with the Apple Watch device type.",
        0xe80000db: "The device is out of storage for apps. Please remove some apps from the device and try again.",
        0xe80000dc: "This app or an app that it contains has a Siri Intents app extension that is missing the IntentsSupported array in the NSExtensionAttributes dictionary in the NSExtension dictionary in its Info.plist.",
        0xe80000dd: "This app or an app that it contains has a Siri Intents app extension that does not correctly define the IntentsRestrictedWhileLocked key in the NSExtensionAttributes dictionary in the NSExtension dictionary in its Info.plist. The key's value must be an array of strings.",
        0xe80000de: "This app or an app that it contains has a Siri Intents app extension that declares values in its IntentsRestrictedWhileLocked key's array value that are not in its IntentsSupported key's array value (in the NSExtensionAttributes dictionary in the NSExtension dictionary in its Info.plist).",
        0xe80000df: "This app or an app that it contains declares multiple Siri Intents app extensions that declare one or more of the same values in the IntentsSupported array in the NSExtensionAttributes dictionary in the NSExtension dictionary in their Info.plist. IntentsSupported must be distinct among a given Siri Intents extension type within an app.",
        0xe80000e0: "The WatchKit 2.0 app, which expects to be compatible with watchOS versions earlier than 3.0, contains a non-WatchKit extension in a location that's not compatible with watchOS versions earlier than 3.0.",
        0xe80000e1: "The WatchKit 2.0 app, which expects to be compatible with watchOS versions earlier than 3.0, contains a framework in a location that's not compatible with watchOS versions earlier than 3.0.",
        0xe80000e2: "kAMDMobileImageMounterDeviceLocked",
        0xe80000e3: "kAMDInvalidSINFError",
        0xe80000e4: "Multiple iMessage app extensions were found in this app. Only one is allowed.",
        0xe80000e5: "This iMessage application is missing its required iMessage app extension.",
        0xe80000e6: "This iMessage application contains an app extension type other than an iMessage app extension. iMessage applications may only contain one iMessage app extension and may not contain other types of app extensions.",
        0xe80000e7: "This app contains a WatchKit app with one or more Siri Intents app extensions that declare IntentsSupported that are not declared in any of the companion app's Siri Intents app extensions. WatchKit Siri Intents extensions' IntentsSupported values must be a subset of the companion app's Siri Intents extensions' IntentsSupported values.",
        0xe80000e8: "kAMDRequireCUPairingCodeError",
        0xe80000e9: "kAMDRequireCUPairingBackoffError",
        0xe80000ea: "kAMDCUPairingError",
        0xe80000eb: "kAMDCUPairingContinueError",
        0xe80000ec: "kAMDCUPairingResetError",
        0xe80000ed: "kAMDRequireCUPairingError",
        0xe80000ee: "kAMDPasswordRequiredError",
        # Errors without id->string mapping.
        0xe8008001: "An unknown error has occurred.",
        0xe8008002: "Attempted to modify an immutable provisioning profile.",
        0xe8008003: "This provisioning profile is malformed.",
        0xe8008004: "This provisioning profile does not have a valid signature (or it has a valid, but untrusted signature).",
        0xe8008005: "This provisioning profile is malformed.",
        0xe8008006: "This provisioning profile is malformed.",
        0xe8008007: "This provisioning profile is malformed.",
        0xe8008008: "This provisioning profile is malformed.",
        0xe8008009: "The signature was not valid.",
        0xe800800a: "Unable to allocate memory.",
        0xe800800b: "A file operation failed.",
        0xe800800c: "There was an error communicating with your device.",
        0xe800800d: "There was an error communicating with your device.",
        0xe800800e: "This provisioning profile does not have a valid signature (or it has a valid, but untrusted signature).",
        0xe800800f: "The application's signature is valid but it does not match the expected hash.",
        0xe8008010: "This provisioning profile is unsupported.",
        0xe8008011: "This provisioning profile has expired.",
        0xe8008012: "This provisioning profile cannot be installed on this device.",
        0xe8008013: "This provisioning profile does not have a valid signature (or it has a valid, but untrusted signature).",
        0xe8008014: "The executable contains an invalid signature.",
        0xe8008015: "A valid provisioning profile for this executable was not found.",
        0xe8008016: "The executable was signed with invalid entitlements.",
        0xe8008017: "A signed resource has been added, modified, or deleted.",
        0xe8008018: "The identity used to sign the executable is no longer valid.",
        0xe8008019: "The application does not have a valid signature.",
        0xe800801a: "This provisioning profile does not have a valid signature (or it has a valid, but untrusted signature).",
        0xe800801b: "There was an error communicating with your device.",
        0xe800801c: "No code signature found.",
        0xe800801d: "Rejected by policy.",
        0xe800801e: "The requested profile does not exist (it may have been removed).",
        0xe800801f: "Attempted to install a Beta profile without the proper entitlement.",
        0xe8008020: "Attempted to install a Beta profile over lockdown connection.",
        0xe8008021: "The maximum number of apps for free development profiles has been reached.",
        0xe8008022: "An error occured while accessing the profile database.",
        0xe8008023: "An error occured while communicating with the agent.",
        0xe8008024: "The provisioning profile is banned.",
        0xe8008025: "The user did not explicitly trust the provisioning profile.",
        0xe8008026: "The provisioning profile requires online authorization.",
        0xe8008027: "The cdhash is not in the trust cache.",
        0xe8008028: "Invalid arguments or option combination.",
    }
    return _error_code_to_message.get(error_code, 'Unknown Error')

class MobileDeviceError(Exception):
    def __init__(self, error_code):
        self.error_code = error_code
        self.error_message = _get_mobile_device_error(error_code)
    def __repr__(self):
        return '{}: {}'.format(self.error_code, self.error_message)
    def __str__(self):
        return '{}: {}'.format(self.error_code, self.error_message)

# ws2_32.dll

if sys.platform == 'win32':
    ws2_32 = ctypes.WinDLL('ws2_32.dll')

    socket_close = ws2_32.closesocket
    socket_close.argtypes = [ctypes.c_uint]
    socket_close.restype = ctypes.c_int

    socket_recv = ws2_32.recv
    socket_recv.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    socket_recv.restype = ctypes.c_int

    socket_send = ws2_32.send
    socket_send.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    socket_send.restype = ctypes.c_int

    socket_setsockopt = ws2_32.setsockopt
    socket_setsockopt.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
    socket_setsockopt.restype = ctypes.c_int

    SOL_SOCKET = 0xffff
    SO_SNDTIMEO = 0x1005
    SO_RCVTIMEO = 0x1006

    class MockSocket(object):
        """
        Python doesn't provide a way to get a socket-like object from a socket
        descriptor, so this implements just enough of the interface for what we
        need.
        """

        def __init__(self, socketDescriptor):
            self._socket = socketDescriptor

        def send(self, data):
            return socket_send(self._socket, data, len(data), 0)

        def sendall(self, data):
            while data:
                result = self.send(data)
                if result < 0:
                    raise RuntimeError('Error sending data: %d' % result)
                data = data[result:]

        def recv(self, bytes):
            data = ctypes.create_string_buffer(bytes)
            result = socket_recv(self._socket, data, bytes, 0)
            if result < 0:
                raise RuntimeError('Error receiving data: %d' % result)
            return data.raw[:result]

        def close(self):
            socket_close(self._socket)
            self._socket = None

        def settimeout(self, timeout):
            ms = int(timeout * 1000)
            value = ctypes.c_int(ms)
            e = socket_setsockopt(self._socket, SOL_SOCKET, SO_SNDTIMEO, ctypes.byref(value), 4)
            if e != 0:
                raise RuntimeError('setsockopt returned %d' % e)
            e = socket_setsockopt(self._socket, SOL_SOCKET, SO_RCVTIMEO, ctypes.byref(value), 4)
            if e != 0:
                raise RuntimeError('setsockopt returned %d' % e)

class SecureService(object):
    def __init__(self, service_connection):
        self._service_connection = service_connection

    def sendall(self, data):
        bytes_sent = AMDServiceConnectionSend(self._service_connection, data, len(data))
        if bytes_sent != len(data):
            raise RuntimeError('Sent {} bytes but was expecting to send {}'.format(bytes_sent, len(data)))

    def recv(self, length):
        data = ctypes.create_string_buffer(length)
        try:
            received = AMDServiceConnectionReceive(self._service_connection, data, ctypes.c_uint32(length))
            return data.raw[:received]
        except Exception as e:
            print(e)

class SecurePlistService(SecureService):

    def build_plist(self, d, endianity='>', fmt=plistlib.FMT_XML):
        payload = plistlib.dumps(d, fmt=fmt)
        message = struct.pack(endianity + 'L', len(payload))
        return message + payload

    def send_plist(self, data, endianity='>', fmt=plistlib.FMT_XML):
        plist = self.build_plist(data, endianity, fmt)
        return self.sendall(plist)

    def recv_prefixed(self, endianity='>'):
        size = self.recv(4)
        if not size or len(size) != 4:
            return
        size = struct.unpack(endianity + 'L', size)[0]
        return self.recv(size)

    def recv_plist(self, endianity='>'):
        data = self.recv_prefixed(endianity=endianity)
        return plistlib.loads(data)

# Finally, the good stuff.

class MobileDeviceManager(object):
    """
    Presents interesting parts of Apple's MobileDevice framework as a much more
    Python-friendly way.

    Usage is generally like this:
        mdm = MobileDeviceManager()
        mdm.waitForDevice()
        mdm.connect()

        # do things with the connected device...
        mdm.installApplication('build/MyApp.app')

        mdm.disconnect()
        mdm.close()
    """

    def __init__(self):
        self._device = None
        self._waitForDeviceId = None
        self._notification = None
        self._last_status = None

        self._transferCallback = am_device_install_application_callback(self._transfer)
        self._installCallback = am_device_install_application_callback(self._install)
        self._uninstallCallback = am_device_install_application_callback(self._uninstall)
        self._timerCallback = cf_run_loop_timer_callback(self._timer)

    def close(self):
        if self._device:
            self._device = None
        if self._notification:
            AMDeviceNotificationUnsubscribe(self._notification)
            self._notification = None

    def connect(self):
        e = AMDeviceConnect(self._device)
        if e != 0:
            raise MobileDeviceError(e)

        if not self.isPaired():
            self.pair()
        self.validatePairing()

    def disconnect(self):
        e = AMDeviceDisconnect(self._device)
        if e != 0:
            raise MobileDeviceError(e)

    def pair(self):
        e = AMDevicePair(self._device)
        if e != 0:
            raise MobileDeviceError(e)

    def isPaired(self):
        return AMDeviceIsPaired(self._device) != 0

    def validatePairing(self):
        e = AMDeviceValidatePairing(self._device)
        if e != 0:
            raise MobileDeviceError(e)

    def startSession(self):
        e = AMDeviceStartSession(self._device)
        if e != 0:
            raise MobileDeviceError(e)

    def stopSession(self):
        e = AMDeviceStopSession(self._device)
        if e != 0:
            raise MobileDeviceError(e)

    def waitForDevice(self, timeout=0, device=None):
        self._waitForDeviceId = device
        self._notification = ctypes.c_void_p()
        self._notificationCallback = am_device_notification_callback(self._deviceNotification)
        e = AMDeviceNotificationSubscribe(self._notificationCallback, 0, 0, 0, ctypes.byref(self._notification))
        if e != 0:
            raise MobileDeviceError(e)

        if timeout > 0:
            timer = CFRunLoopTimerCreate(None, CFAbsoluteTimeGetCurrent() + timeout, 0, 0, 0, self._timerCallback, None)
            CFRunLoopAddTimer(CFRunLoopGetCurrent(), timer, kCFRunLoopCommonModes)

        CFRunLoopRun()
        if timeout > 0:
            CFRunLoopRemoveTimer(CFRunLoopGetCurrent(), timer, kCFRunLoopCommonModes)
        return self._device

    def productVersion(self):
        self.connect()
        try:
            return CFStringGetStr(AMDeviceCopyValue(self._device, None, CFStr("ProductVersion")))
        finally:
            self.disconnect()

    def buildVersion(self):
        self.connect()
        try:
            return CFStringGetStr(AMDeviceCopyValue(self._device, None, CFStr("BuildVersion")))
        finally:
            self.disconnect()

    def connectionId(self):
        return AMDeviceGetConnectionID(self._device)

    def deviceId(self):
        return CFStringGetStr(AMDeviceCopyDeviceIdentifier(self._device))

    def listImages(self):
        images = []
        imageMounterService = self.startSecureService('com.apple.mobile.mobile_image_mounter')
        try:
            plistService = SecurePlistService(imageMounterService)
            plistService.send_plist({'Command': 'CopyDevices'})
            result = plistService.recv_plist()
            if result.get('Status') == 'Complete':
                images = result.get('EntryList', [])
            plistService.send_plist({'Command': 'Hangup'})
        finally:
            self.stopSecureService(imageMounterService)
        return images

    def lookupImage(self, imageType):
        signature = None
        imageMounterService = self.startSecureService('com.apple.mobile.mobile_image_mounter')
        try:
            plistService = SecurePlistService(imageMounterService)
            plistService.send_plist({
                'Command': 'LookupImage',
                'ImageType': imageType
            })
            result = plistService.recv_plist()
            signature = result.get('ImageSignature', [])
            if isinstance(signature, list):
                if len(signature) > 0:
                    signature = signature[0]
                else:
                    signature = None

            plistService.send_plist({'Command': 'Hangup'})
        finally:
            self.stopSecureService(imageMounterService)
        return signature

    def isDeveloperImageMounted(self):
        return self.lookupImage('Developer') is not None

    def unmountImage(self):
        images = self.listImages()
        for image in images:
            if image.get('DiskImageType', '')  == 'Developer':
                imageSignature = image.get('ImageSignature', '')
                mountPath = image.get('MountPath', '')
                imageMounterService = self.startSecureService('com.apple.mobile.mobile_image_mounter')
                try:
                    plistService = SecurePlistService(imageMounterService)
                    plistService.send_plist({
                        'Command': 'UnmountImage',
                        'ImageType': 'Developer',
                        'MountPath': mountPath,
                        'ImageSignature': imageSignature
                    })
                    response = plistService.recv_plist()
                    error = response.get('Error')
                    if error:
                        print("UnmountImage returned: {}".format(error))
                    plistService.send_plist({'Command': 'Hangup'})
                finally:
                    self.stopSecureService(imageMounterService)

    def mountImage(self, imagePath):
        imageSignature = Path(Path(imagePath).with_suffix('.dmg.signature')).read_bytes()
        mountedSignature = self.lookupImage('Developer')
        if mountedSignature == imageSignature:
            print('MountImage => AlreadyMounted')
            return

        imageMounterService = self.startSecureService('com.apple.mobile.mobile_image_mounter')
        try:
            plistService = SecurePlistService(imageMounterService)

            plistService.send_plist({
                'Command': 'ReceiveBytes',
                'ImageSize': os.stat(imagePath).st_size,
                'ImageType': 'Developer',
                'ImageSignature': imageSignature
            })
            result = plistService.recv_plist()

            if result.get('Status') != 'ReceiveBytesAck':
                raise RuntimeError('Expected "ReceiveBytesAck", got {}'.format(result))

            # Send the image to the device
            plistService.sendall(open(imagePath, 'rb').read())
            result = plistService.recv_plist()
            if result.get('Status') != 'Complete':
                raise RuntimeError('Expected "Complete", got {}'.format(result))

            # Mount the image
            plistService.send_plist({
                'Command': 'MountImage',
                'ImageType': 'Developer',
                'ImageSignature': imageSignature
            })
            result = plistService.recv_plist()
            if 'Error' in result:
                print('MountImage returned', result['Error'])
            if 'Status' in result:
                print('MountImage =>', result['Status'])

            plistService.send_plist({'Command': 'Hangup'})

        finally:
            self.stopSecureService(imageMounterService)

    def startService(self, service):
        self.connect()
        try:
            self.startSession()
            try:
                fd = ctypes.c_int()
                e = AMDeviceStartService(self._device, CFStr(service), ctypes.byref(fd), None)
                if e != 0:
                    raise MobileDeviceError(e)
                return fd.value
            finally:
                self.stopSession()
        finally:
            self.disconnect()

    def startHouseArrestService(self, bundleId):
        self.connect()
        try:
            self.startSession()
            try:
                fd = ctypes.c_int()
                e = AMDeviceStartHouseArrestService(self._device, CFStr(bundleId), None, ctypes.byref(fd), None)
                if e != 0:
                    raise MobileDeviceError(e)
                return fd.value
            finally:
                self.stopSession()
        finally:
            self.disconnect()

    def startSecureService(self, service):
        self.connect()
        try:
            self.startSession()
            try:
                handle = ctypes.c_void_p()
                e = AMDeviceSecureStartService(self._device, CFStr(service), None, ctypes.byref(handle))
                if e != 0:
                    raise MobileDeviceError(e)
                return handle
            finally:
                self.stopSession()
        finally:
            self.disconnect()

    def stopSecureService(self, handle):
        if handle:
            self.connect()
            self.startSession()
            AMDServiceConnectionInvalidate(handle)
            self.stopSession()
            self.disconnect()

    def readPlist(self, path):
        plist = {}
        try:
            f = open(path, 'rb')
            plist = plistlib.load(f)
            f.close()
        except:
            raise RuntimeError('Unable to load plist: {}'.format(path))
        return plist

    def bundleId(self, path):
        plist = self.readPlist(os.path.join(path, 'Info.plist'))
        return plist['CFBundleIdentifier']

    def bundleExecutable(self, path):
        plist = self.readPlist(os.path.join(path, 'Info.plist'))
        return plist['CFBundleExecutable']

    def transferApplication(self, path):
        afc = self.startService("com.apple.afc")
        try:
            e = AMDeviceTransferApplication(afc, CFStr(os.path.abspath(path)), None, self._transferCallback, None)
            if e != 0:
                raise MobileDeviceError(e)
        finally:
            self.stopService(afc)

    def installApplication(self, path):
        afc = mdm.startService("com.apple.mobile.installation_proxy")
        try:

            items = 1
            keys = (ctypes.c_void_p * items)(CFStr('PackageType'))
            values = (ctypes.c_void_p * items)(CFStr('Developer'))

            options = CFDictionaryCreate(None, keys, values, items, ctypes.byref(kCFTypeDictionaryKeyCallBacks), ctypes.byref(kCFTypeDictionaryValueCallBacks))

            e = AMDeviceInstallApplication(afc, CFStr(path), options, self._installCallback, None)
            if e != 0:
                raise MobileDeviceError(e)
        finally:
            mdm.stopService(afc)

    def uninstallApplication(self, bundleId):
        afc = self.startService("com.apple.mobile.installation_proxy")
        try:
            e = AMDeviceUninstallApplication(afc, CFStr(bundleId), None, self._uninstallCallback, None)
            if e != 0:
                raise MobileDeviceError(e)
        finally:
            self.stopService(afc)

        items = 1

    def lookupApplications(self):
        self.connect()
        try:
            self.startSession()
            try:
                dictionary = CFDictionaryRef()
                e = AMDeviceLookupApplications(self._device, 0, ctypes.byref(dictionary))
                if e != 0:
                    raise MobileDeviceError(e)
                return CFDictionaryToDict(dictionary)
            finally:
                self.stopSession()
        finally:
            self.disconnect()

    def lookupApplicationExecutable(self, identifier):
        dictionary = self.lookupApplications()
        try:
            return '%s/%s' % (dictionary[identifier]['Path'], dictionary[identifier]['CFBundleExecutable'])
        except KeyError:
            raise RuntimeError('%s not found in app list.' % identifier)

    def stopService(self, fd):
        if sys.platform == 'win32':
            ws2_32.closesocket(fd)
        else:
            os.close(fd)

    def showStatus(self, action, dictionary):
        show = ['[{}]'.format(action)]

        percentComplete = CFDictionaryGetValue(dictionary, CFStr('PercentComplete'))
        if percentComplete:
            percent = ctypes.c_int()
            CFNumberGetValue(percentComplete, kCFNumberSInt32Type, ctypes.byref(percent))
            show.append(str.rjust('{}%'.format(percent.value), 4))

        show.append(CFStringGetStr(CFDictionaryGetValue(dictionary, CFStr('Status'))))

        path = CFDictionaryGetValue(dictionary, CFStr('Path'))
        if path:
            show.append(CFStringGetStr(path))

        status = ' '.join(show)
        if self._last_status != status:
            print(status)
            self._last_status = status

    def debugServer(self):
        service = self.startSecureService('com.apple.debugserver.DVTSecureSocketProxy')
        return service

    def _timer(self, timer, info):
        CFRunLoopStop(CFRunLoopGetCurrent())

    def _transfer(self, dictionary, user):
        self.showStatus('Transferring', dictionary)
        return 0

    def _install(self, dictionary, user):
        self.showStatus('Installing', dictionary)
        return 0

    def _uninstall(self, dictionary, user):
        self.showStatus('Uninstalling', dictionary)
        return 0

    def _mount(self, dictionary, user):
        self.showStatus('Mounting', dictionary)
        return 0

    def _deviceNotification(self, info, user):
        info = info.contents
        if info.msg == ADNCI_MSG_CONNECTED:
            if self._waitForDeviceId is None or self._waitForDeviceId == CFStringGetStr(AMDeviceCopyDeviceIdentifier(ctypes.c_void_p(info.dev))):
                self._device = ctypes.c_void_p(info.dev)
                CFRunLoopStop(CFRunLoopGetCurrent())
        elif info.msg == ADNCI_MSG_DISCONNECTED:
            self._device = None
        elif info.msg == ADNCI_MSG_UNKNOWN:
            # This happens as we're closing.
            pass
        else:
            raise RuntimeError('Unexpected device notification status: %d' % info.msg)

class AFCFile(object):
    def __init__(self, afc, path, mode):
        self._afc = afc
        self._mode = 0
        if 'r' in mode:
            self._mode |= 1
        if 'w' in mode:
            self._mode |= 2
        self._file = AFCFileRef()
        self._open = False
        result = AFCFileRefOpen(self._afc, path.encode('utf-8'), self._mode, 0, ctypes.byref(self._file))
        if result != 0:
            raise RuntimeError('AFCFileRefOpen returned %d' % result)
        if not self._file:
            raise RuntimeError('AFCFileRefOpen did not open a file')
        self._open = True

    def close(self):
        if self._open:
            result = AFCFileRefClose(self._afc, self._file)
            if result != 0:
                raise RuntimeError('AFCFileRefClose returned %d' % result)
            self._open = False

    def read(self, length):
        readLength = ctypes.c_uint32(length)
        data = (ctypes.c_char * length)()
        result = AFCFileRefRead(self._afc, self._file, data, ctypes.byref(readLength))
        if result != 0:
            raise RuntimeError('AFCFileRefRead returned %d' % result)
        return data.raw[:readLength.value]

    def write(self, data):
        length = ctypes.c_uint(len(data))
        pointer = ctypes.c_char_p(data)
        result = AFCFileRefWrite(self._afc, self._file, pointer, length)
        if result != 0:
            raise RuntimeError('AFCFileRefWrite returned %d' % result)

class AFC(object):
    def __init__(self, session):
        self._session = session
        self._afc = AFCConnectionRef()
        result = AFCConnectionOpen(self._session, 0, ctypes.byref(self._afc))
        if result != 0:
            raise RuntimeError('AFCConnectionOpen returned %d' % result)

    def open(self, path, mode):
        return AFCFile(self._afc, path, mode)

    def close(self):
        AFCConnectionClose(self._afc)

    def mkdir(self, path):
        result = AFCDirectoryCreate(self._afc, path)
        if result != 0:
            raise RuntimeError('AFCDirectoryCreate returned %d' % result)

    def listdir(self, path):
        directory = AFCDirectoryRef()
        result = AFCDirectoryOpen(self._afc, path.encode('utf-8'), ctypes.byref(directory))
        if result != 0:
            raise OSError('AFCDirectoryOpen returned %d' % result)
        name = ctypes.c_char_p()
        entries = []
        while AFCDirectoryRead(self._afc, directory, ctypes.byref(name)) == 0:
            if name.value is None:
                break
            path = name.value.decode('utf-8')
            if not path in ('.', '..'):
                entries.append(path)
        AFCDirectoryClose(self._afc, directory)
        return entries

class DeviceSupportPaths(object):
    """
    A small helper for finding various Xcode directories.

    Written from fruitstrap.c, trial and error, and lldb's
    PlatformRemoteiOS.cpp:
    <https://llvm.org/viewvc/llvm-project/lldb/trunk/source/Plugins/Platform/MacOSX/PlatformRemoteiOS.cpp?view=markup>
    """
    def __init__(self, target, productVersion, buildVersion):
        self._target = target
        self._productVersion = productVersion
        self._buildVersion = buildVersion

        self._deviceSupportDirectory = None
        self._deviceSupportForOsVersion = None
        self._developerDiskImagePath = None

    def deviceSupportDirectory(self):
        if not self._deviceSupportDirectory:
            if sys.platform == 'win32':
                here = os.path.normpath(os.path.abspath(os.path.dirname(__file__)))
                self._deviceSupportDirectory = os.path.join(here, 'DeveloperDiskImage')
            else:
                self._deviceSupportDirectory = subprocess.check_output(['xcode-select', '-print-path']).decode('utf-8').strip()
        return self._deviceSupportDirectory

    def deviceSupportDirectoryForOsVersion(self):
        if not self._deviceSupportForOsVersion:
            path = os.path.join(self.deviceSupportDirectory(), 'Platforms', self._target + '.platform', 'DeviceSupport')

            attempts = [os.path.join(path, attempt) for attempt in self.versionPermutations()]

            for attempt in attempts:
                if os.path.exists(attempt):
                    self._deviceSupportForOsVersion = attempt
                    break
            if not self._deviceSupportForOsVersion:
                raise RuntimeError('Could not find device support directory for %s %s (%s).' % (self._target, self._productVersion, self._buildVersion))
        return self._deviceSupportForOsVersion

    def versionPermutations(self):
            shortProductVersion = '.'.join(self._productVersion.split('.')[:2])
            return [
                '%s (%s)' % (self._productVersion, self._buildVersion),
                '%s (%s)' % (shortProductVersion, self._buildVersion),
                '%s' % self._productVersion,
                '%s' % shortProductVersion,
                'Latest',
            ]

    def developerDiskImagePath(self):
        if not self._developerDiskImagePath:
            if sys.platform == 'win32':
                path = self.deviceSupportDirectory()
            else:
                path = os.path.join(self.deviceSupportDirectory(), 'Platforms', self._target + '.platform', 'DeviceSupport')
            attempts = [os.path.join(path, attempt, 'DeveloperDiskImage.dmg') for attempt in self.versionPermutations()]
            for attempt in attempts:
                if os.path.exists(attempt):
                    self._developerDiskImagePath = attempt
                    break
            if not self._developerDiskImagePath:
                raise RuntimeError('Could not find developer disk image for %s %s (%s).' % (self._target, self._productVersion, self._buildVersion))
        return self._developerDiskImagePath

class DebuggerException(Exception):
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return '{}'.format(self.value)
    def __str__(self):
        return '{}'.format(self.value)

class GdbServer(object):
    """
    Given a handle to the iOS remote debugserver service, this speaks just enough
    of the GDB Remote Serial Protocol
    <http://sourceware.org/gdb/onlinedocs/gdb/Remote-Protocol.html> to launch
    an application and display its output.

    Usage:
        GdbServer(connectedSocket).run('/path/to/executable', 'arg1', 'arg2')
    """
    def __init__(self, serviceConnection):
        self._connection = serviceConnection
        self._service = SecureService(serviceConnection)
        self.exitCode = None
        self._readBuffer = ''

    def read(self):
        startIndex = self._readBuffer.find('$')
        endIndex = self._readBuffer.find('#', startIndex)
        while startIndex == -1 or endIndex == -1 or len(self._readBuffer) < endIndex + 3:
            data = self._service.recv(4096)
            if not data:
                break
            self._readBuffer += data.decode('utf-8')
            startIndex = self._readBuffer.find('$')
            endIndex = self._readBuffer.find('#', startIndex)

        # Discard any ACKs.  We trust we're on a reliable connection.
        while self._readBuffer.startswith('+'):
            self._readBuffer = self._readBuffer[1:]

        payload = None
        startIndex = self._readBuffer.find('$')
        endIndex = self._readBuffer.find('#', startIndex)
        if startIndex != -1 and endIndex != -1 and len(self._readBuffer) >= endIndex + 3:
            payload = self._readBuffer[startIndex + 1:endIndex]
            checksum = self._readBuffer[endIndex + 1:endIndex + 3]
            if checksum != '00':
                calculated = '%02x' % (sum(ord(c) for c in payload) & 255)
                if checksum != calculated:
                    raise RuntimeError('Bad response checksum (%s vs %s).' % (checksum, calculated))

        self._readBuffer = self._readBuffer[endIndex + 3:]

        return payload

    def _send(self, packet):
        payload = '$%s#%02x' % (packet, sum(ord(c) for c in packet) & 255)
        message = struct.pack('>L', len(payload)) + bytes(payload, 'utf-8')
        self._service.sendall(message)

    def send(self, packet):
        self._send(packet)

        stopReply = [True for command in ['C', 'c', 'S', 's', 'vCont', 'vAttach', 'vRun', 'vStopped', '?'] if packet.startswith(command)]

        if stopReply:
            resume = True
            while resume:
                resume = False
                response = self.read()
                if response:
                    if response.startswith('S'):
                        signal = '0x' + response[1:3]
                        message = 'Program received signal %s.' % signal
                        raise DebuggerException(message)
                    elif response.startswith('T'):
                        signal = '0x' + response[1:3]
                        message = 'Program received signal %s.' % signal
                        for pair in response[4:].split(';'):
                            message += '\n%s' % pair
                        raise DebuggerException(message)
                    elif response.startswith('W'):
                        self.exitCode = int(response[1:], 16)
                        print('Process returned %d.' % self.exitCode)
                    elif response.startswith('X'):
                        signal = '0x' + response[1:3]
                        if ';' in response:
                            response = response.split(';', 1)[1]
                        raise DebuggerException('Process terminated with signal %s (%s).' % (signal, response))
                    elif response.startswith('O'):
                        log_output = binascii.unhexlify(bytes(response[1:],'utf-8')).decode('utf-8')
                        print('{}'.format(log_output), end=' ')
                        resume = True
                    elif response.startswith('F'):
                        raise RuntimeError('GDB File-I/O Remote Protocol Unimplemented.')
                    else:
                        raise RuntimeError('Unexpected response to stop reply packet: ' + response)
        else:
            response = self.read()
        return response

    def run(self, *argv):
        self.send('QStartNoAckMode')
        self._send('+')
        self.send('QEnvironmentHexEncoded:')
        self.send('QSetDisableASLR:1')
        args_command = 'A'
        for i,arg in enumerate(argv):
            args_command += '{},{},{},'.format(len(arg) * 2, i, binascii.hexlify(bytes(arg, 'utf-8')).decode('utf-8'))
        self.send(args_command)
        self.send('qLaunchSuccess')
        self.send('vCont;c')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manage and launch applications on iOS.')

    group = parser.add_argument_group('Global Configuration')
    group.add_argument('-b', '--bundle', help='path to local app bundle to operate on')
    group.add_argument('-id', '--appid', help='application identifier to operate on')
    group.add_argument('-t', '--timeout', type=int, help='seconds to wait for slow operations before giving up', default=0)
    group.add_argument('-dev', '--device-id', help='device id of specific device to communicate with')

    group = parser.add_argument_group('Application Management')
    group.add_argument('-i', '--install', action='store_true', help='install an application')
    group.add_argument('-u', '--uninstall', action='store_true', help='uninstall an application')
    group.add_argument('-l', '--list-applications', action='store_true', help='list installed applications')

    group.add_argument('-r', '--run', action='store_true', help='run an application')
    group.add_argument('-a', '--arguments', nargs=argparse.REMAINDER, help='arguments to pass to application being run')

    group = parser.add_argument_group('Developer Disk Image')
    group.add_argument('-m', '--mount', action='store_true', help='mount developer disk image (must be done at least once to run)')
    group.add_argument('-ddi', '--developer-disk-image', type=str, help='path to DeveloperDiskImage.dmg')

    group = parser.add_argument_group('File Access')
    group.add_argument('-get', '--get-file', nargs=2, metavar=('DEVICE_FILE', 'LOCAL_FILE'), help='read a file from the device')
    group.add_argument('-put', '--put-file', nargs=2, metavar=('LOCAL_FILE', 'DEVICE_FILE'), help='write a file to the device')
    group.add_argument('-ls', '--list-files', nargs='?', metavar='PATH', const='.', help='recursively list all files and directories, starting at the root or given path')

    arguments = parser.parse_args()

    if not arguments.install \
        and not arguments.uninstall \
        and not arguments.run \
        and not arguments.list_applications \
        and not arguments.mount \
        and not arguments.get_file \
        and not arguments.put_file \
        and not arguments.list_files:
        print('Nothing to do.')
        sys.exit(0)

    mdm = MobileDeviceManager()
    if arguments.device_id:
        print('Waiting for a device with UDID %s...' % arguments.device_id)
    else:
        print('Waiting for a device...')
    if not mdm.waitForDevice(timeout=arguments.timeout, device=arguments.device_id):
        print('Gave up waiting for a device.')
        sys.exit(1)

    print('Connected to device with UDID:', mdm.deviceId())

    if arguments.uninstall:
        bundle = arguments.appid or mdm.bundleId(arguments.bundle)
        print('\nUninstalling %s...' % bundle)
        mdm.uninstallApplication(bundle)

    if arguments.install:
        print('\nInstalling %s...' % arguments.bundle)
        mdm.transferApplication(arguments.bundle)
        mdm.installApplication(arguments.bundle)

    if arguments.list_applications:
        print('\nInstalled applications:')
        applications = mdm.lookupApplications()
        bundleIdentifiers = list(applications.keys())
        bundleIdentifiers.sort()
        for bundleId in bundleIdentifiers:
            print(bundleId)

    if arguments.mount:
        if arguments.developer_disk_image:
            ddi = arguments.developer_disk_image
        else:
            ddi = DeviceSupportPaths('iPhoneOS', mdm.productVersion(), mdm.buildVersion()).developerDiskImagePath()
        print('\nMounting %s...' % ddi)
        mdm.mountImage(ddi)

    if arguments.run:
        executable = mdm.lookupApplicationExecutable(arguments.appid or mdm.bundleId(arguments.bundle))
        db = mdm.debugServer()
        #if arguments.timeout > 0:
        #    db.settimeout(arguments.timeout)
        debugger = GdbServer(db)
        argv = [executable]
        if arguments.arguments:
            argv += arguments.arguments
        print('\nRunning %s...' % ' '.join(argv))
        try:
            debugger.run(*argv)
        except DebuggerException as e:
            print(e)
            sys.exit(1)
        sys.exit(debugger.exitCode)

    if arguments.get_file or arguments.put_file or arguments.list_files:
        if arguments.appid or arguments.bundle:
            afc = AFC(mdm.startHouseArrestService(arguments.appid or mdm.bundleId(arguments.bundle)))
        else:
            afc = AFC(mdm.startService(u'com.apple.afc'))

        if arguments.get_file:
            readFile = afc.open(arguments.get_file[0], 'r')
            writeFile = open(arguments.get_file[1], 'wb')
            size = 0
            while True:
                data = readFile.read(8192)
                if not data:
                    break
                writeFile.write(data)
                size += len(data)
            writeFile.close()
            readFile.close()
            print('%d bytes read from %s.' % (size, arguments.get_file[0]))
        elif arguments.put_file:
            readFile = open(arguments.put_file[0], 'rb')
            writeFile = afc.open(arguments.put_file[1], 'w')
            size = 0
            while True:
                data = readFile.read(8192)
                if not data:
                    break
                writeFile.write(data)
                size += len(data)
            writeFile.close()
            readFile.close()
            print('%d bytes written to %s.' % (size, arguments.put_file[1]))
        elif arguments.list_files:
            print('Listing %s:' % arguments.list_files)
            def walk(root, indent=0):
                print('  ' * indent + root)
                try:
                    children = afc.listdir(root)
                except:
                    children = []
                for child in children:
                    walk(root.rstrip('/') + '/' + child, indent + 1)
            walk(arguments.list_files)
        afc.close()

    mdm.close()

