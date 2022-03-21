fruitstrap
==========
Install and run iPhone apps without using Xcode. Designed to work on unjailbroken devices.

## Requirements

* You need to have a valid iPhone development certificate installed (or at least a correctly signed iOS app).
* Access to a Mac with Xcode installed to get access to the DeveloperDiskImage as needed.

## Usage

* Install an application bundle, mount the developer disk image, and run it
* `apple.py -b/--bundle <app>  -i  -r -a <args>`

## Notes

* Tested on MacOS and Win64.
* Win64 requires installation of the Apple Mobile Device Support package. This can be extracted from the iTunes Win64 installer.
* With some modifications, it may be possible to use this without Xcode installed; however, you would need a copy of the relevant DeveloperDiskImage.dmg (included with Xcode).
