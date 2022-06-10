Python scripts to download Qt libraries from download.qt.io and its mirrors.

There are 2 problems with the existing Qt installers:
1. There is no out-of-the-box tool to download Qt libraries when <https://download.qt.io> is unavailable.
2. Only <https://download.qt.io> provides SHA256 hashes. Even if the first problem is solved, there is no way to verify the downloaded archives.

The scripts are a workaround for those problems:<br>
When <https://download.qt.io> is available, `get_data.py` can be used to get the mirror list, the link list and SHA256 hashes for the required Qt versions. Then, obtained `.json` files can be stored somewhere for future use.<br>
With obtained `.json` files, `qti.py` can be used to download and verify the hashes of the archives from Qt mirrors even when <https://download.qt.io> is unavailable.


## Requirements

1. `python 3.9+`
2. `7z`

The scripts were tested on Linux only.


## Usage

### Fetch info
Fetch the mirror list, the archive list and the hashes.<br>
<https://download.qt.io> must be available at this point.<br>
This repository includes the info obtained at 8 June 2022.

<br>

Fetch the mirror list and save it to `data/mirrors.json`.
```
$ ./get_data.py -m mirrors
```

<br>

Fetch available versions and save them to `data/versions.json`.
```
$ ./get_data.py -m versions
```

<br>

Print data from `data/versions.json` to figure out the name of the needed version.<br>
For example, if the user needs Windows desktop 5.15.2:
```
$ ./get_data.py
windows_x86
linux_x64
mac_x64
$ ./get_data.py -q windows_x86
winrt
android
desktop
$ ./get_data.py -q windows_x86 desktop
...
qt5_51210
qt5_5152_wasm
qt5_5152
qt5_5151_wasm
qt5_5151
...
```

<br>

Fetch the list of links and SHA256 hashes for the required version and save them to `data/<OS>/<platform>/<qt-version>.json`, e.g. `data/windows_x86/desktop/qt5_5152.json`.
```
$ ./get_data.py -m hashes -q windows_x86 desktop qt5_5152
```

<br>

Fetch lists of links and SHA256 hashes for all OSs, platforms, versions and save them to `data/<OS>/<platform>/<qt-version>.json` files.<br>
This takes a while, around 20 minutes with 100 processes, 7-10 minutes with 400 processes (default).
```
$ ./get_data.py -m hashes
```

<br>

### Download
Download and unpack archives from <https://download.qt.io> and its mirrors.<br>
Requires `.json` files from the previous step.<br>
Should work as long as at least one mirror from `data/mirrors.json` is available.

<br>

Print available archives to figure out the names of the needed archives.<br>
For example, if the user needs Windows desktop 5.15.2 MSVC2019 x64 Qt Charts archive:
```
$ ./qti.py
linux_x64
mac_x64
windows_x86
$ ./qti.py -q windows_x86
android
desktop
winrt
$ ./qti.py -q windows_x86 desktop
...
qt5_5151
qt5_5151_wasm
qt5_5152
qt5_5152_wasm
qt5_59
...
$ ./qti.py -q windows_x86 desktop qt5_5152
...
win64_mingw81
win64_msvc2015_64
win64_msvc2019_64
$ ./qti.py -q windows_x86 desktop qt5_5152 win64_msvc2019_64
...
qtbase
qtcharts
qtconnectivity
...
```

<br>

Download Qt Charts archive to `archives` and unpack it to `out`.
```
$ ./qti.py -m download -q windows_x86 desktop qt5_5152 win64_msvc2019_64 -a qtcharts
```

<br>

Download all archives for the selected version/arch to `archives` and unpack them to `out`.
```
$ ./qti.py -m download -q windows_x86 desktop qt5_5152 win64_msvc2019_64 -a all
```

<br>

## Notes

If an archive is already found in `archives` directory, and the hash matches, it's not redownloaded.

In case of a hash mismatch after a successful download, the script will exit with an error.

There is no dependency resolution.

The scripts can handle only libraries and debug info for those libraries. There is no support to download tools, source code, etc.


## Inspired by

<https://github.com/miurahr/aqtinstall>

<https://github.com/WillBrennan/yaqti>
