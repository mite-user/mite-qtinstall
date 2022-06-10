#! /usr/bin/env python3

# Requires:
#     Python 3.9+
#     7z

import argparse
import contextlib
import os
import os.path
import secrets
import subprocess
import sys

import qti_util


def argparse_parse(argv):
    script_dir = os.path.dirname(__file__)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="There are 2 modes:\n"
                    "1. print available archives;\n"
                    "2. download and unpack archives from a random qt mirror.")
    parser.add_argument(
        "-m", "--mode",
        default="print",
        choices=["print", "download"],
        help="Mode of operation.\n"
             "Default: print")
    parser.add_argument(
        "-d", "--data-dir",
        default=os.path.join(script_dir, "data"),
        help="The folder with input JSON.\n"
             "Default: <script-dir>/data")
    parser.add_argument(
        "-q", "--qt-version",
        nargs="*",
        default=[""],
        help="'OS', 'platform', 'qt-version', 'arch'\n"
             "    for which to print/download archives.\n"
             "In 'print' mode:\n"
             "    if empty, prints available OSs,\n"
             "    if only OS is specified, prints available platforms,\n"
             "    etc.")
    parser.add_argument(
        "-c", "--archives-dir",
        default=os.path.join(script_dir, "archives"),
        help="In 'download' mode,\n"
             "    the folder to store downloaded archives.\n"
             "Default: <script-dir>/archives")
    parser.add_argument(
        "-o", "--out-dir",
        default=os.path.join(script_dir, "out"),
        help="In 'download' mode, the folder to store unpacked files.\n"
             "Default: <script-dir>/out")
    parser.add_argument(
        "-a", "--archives",
        nargs="*",
        default=["qtbase"],
        help="In 'download' mode, the archives to download.\n"
             "    If 'all' is specified, select all archives.\n"
             "Default: qtbase")
    parser.add_argument(
        "-z", "--exe-7z",
        nargs="*",
        default=["7z"],
        help="The command to invoke 7z executable.\n"
             "Default: 7z")
    parser.add_argument(
        "-s", "--skip-unpack",
        action=argparse.BooleanOptionalAction,
        help="In 'download' mode,\n"
             "    don't unpack and don't delete downloaded archives.")
    parser.add_argument(
        "-k", "--keep-archives",
        action=argparse.BooleanOptionalAction,
        help="In 'download' mode, don't delete downloaded archives.")
    parser.add_argument(
        "-w", "--async-opts",
        nargs=2,
        default=[5, 10],
        type=float,
        help="In 'download' mode, async download options:\n"
             "1. number of worker processes;\n"
             "2. delay in seconds between progress prints.\n"
             "Default: 5 10")
    parser.add_argument(
        "-r", "--req-opts",
        nargs=3,
        default=[15, 5, 3],
        type=float,
        help="Request options:\n"
             "1. timeout in seconds;\n"
             "2. delay between attempts in seconds;\n"
             "3. number of attempts.\n"
             "Default: 15 5 3")
    return parser.parse_args(args=argv[1:])


def print_archives(args):
    OS, platform, ver, arch = qti_util.force_len(args.qt_version, 4)
    path = os.path.join(args.data_dir, OS, platform, ver)
    if OS and platform and ver:
        archives_per_arch = qti_util.load_JSON(f"{path}.json")
        if arch:
            qti_util.print_list(sorted(archives_per_arch[arch]))
        else:
            qti_util.print_list(sorted(archives_per_arch.keys()))
    elif OS and platform:
        version_JSONs = qti_util.get_files(path)
        versions = [v.removesuffix(".json") for v in version_JSONs]
        qti_util.print_list(sorted(versions))
    else:
        qti_util.print_list(sorted(qti_util.get_dirs(path)))


def get_archive_filepath(archive_info, archives_dir):
    archive_filename = archive_info["rel_path"].split("/")[-1]
    return os.path.join(archives_dir, archive_filename)


def _download_archive(archive_info, ver_path, mirror_URL, out_dir, req_opts):
    archive_filepath = get_archive_filepath(archive_info, out_dir)
    try:
        computed_hash = qti_util.compute_hash(archive_filepath,
                                              qti_util.HASH_ALG)
    except FileNotFoundError:
        computed_hash = ""
    if computed_hash and computed_hash == archive_info[qti_util.HASH_ALG]:
        return
    archive_URL = (f"{mirror_URL}/online/qtsdkrepository"
                   f"/{ver_path}/{archive_info['rel_path']}")
    qti_util.retrieve_URL(archive_URL, archive_filepath, req_opts)
    computed_hash = qti_util.compute_hash(archive_filepath,
                                          qti_util.HASH_ALG)
    if computed_hash and computed_hash == archive_info[qti_util.HASH_ALG]:
        return
    raise qti_util.HashMismathError(
              "Hash mismatch of just downloaded file\n"
              f"    expected {archive_info[qti_util.HASH_ALG]}\n"
              f"    computed {computed_hash}\n"
              f"    for file {archive_filepath}\n"
              f"    downloaded from {archive_URL}")


def download_archives(archives,
                      ver_path,
                      mirrors,
                      out_dir,
                      async_opts,
                      req_opts):
    working_mirrors = mirrors
    os.makedirs(out_dir, exist_ok=True)
    while working_mirrors:
        async_args = []
        mirror_URL = secrets.choice(working_mirrors)
        for archive_info in archives.values():
            async_arg = (archive_info, ver_path, mirror_URL, out_dir, req_opts)
            async_args.append(async_arg)
        try:
            print(f"Downloading {len(async_args)} archives\n"
                  f"    from {mirror_URL}")
            qti_util.pool_apply(_download_archive, async_args, async_opts)
            return
        except qti_util.HashMismathError:
            raise
        except Exception as except_obj:
            print(f"{type(except_obj).__name__}: {except_obj}\n"
                  f"Failed to fetch an archive from {mirror_URL}\n"
                  "The mirror will no longer be used for this run.")
            working_mirrors.remove(mirror_URL)
    sys.exit("All mirrors unreachable.")


def extract_7z(file, out_dir, exe_7z):
    command_7z = exe_7z + ["x", "-aoa", "-bd", "-y", f"-o{out_dir}", file]
    subprocess.run(command_7z, stdout=subprocess.PIPE, check=True)


def unpack_archives(archives, archives_dir, out_dir, exe_7z):
    os.makedirs(out_dir, exist_ok=True)
    for archive_info in archives.values():
        archive_filepath = get_archive_filepath(archive_info, archives_dir)
        extract_7z(archive_filepath, out_dir, exe_7z)


def remove_archives(archives, archives_dir):
    for archive_info in archives.values():
        archive_filepath = get_archive_filepath(archive_info, archives_dir)
        os.remove(archive_filepath)
    with contextlib.suppress(OSError):
        os.rmdir(archives_dir)


def download_unpack_archives(args):
    OS, platform, ver, arch = qti_util.force_len(args.qt_version, 4)
    ver_path = f"{OS}/{platform}/{ver}"
    ver_info_JSON = os.path.join(args.data_dir, f"{ver_path}.json")
    available_archives_per_arch = qti_util.load_JSON(ver_info_JSON)
    available_archives = available_archives_per_arch[arch]
    if "all" in args.archives:
        archives = available_archives
    else:
        archives = {}
        for requested_archive in args.archives:
            if requested_archive not in available_archives:
                sys.exit(f"'{requested_archive}' archive not found"
                         f" for arch '{arch}'\n"
                         f"    in {ver_info_JSON}")
            archives[requested_archive] = available_archives[requested_archive]
    mirrors_JSON = os.path.join(args.data_dir, "mirrors.json")
    mirrors = qti_util.load_JSON(mirrors_JSON)
    download_archives(archives,
                      ver_path,
                      mirrors,
                      args.archives_dir,
                      args.async_opts,
                      args.req_opts)
    if not args.skip_unpack:
        unpack_archives(archives, args.archives_dir, args.out_dir, args.exe_7z)
        if not args.keep_archives:
            remove_archives(archives, args.archives_dir)


def main(args):
    args = argparse_parse(sys.argv)
    if args.mode == "print":
        print_archives(args)
    elif args.mode == "download":
        download_unpack_archives(args)


if __name__ == "__main__":
    main(sys.argv)
