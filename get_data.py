#! /usr/bin/env python3

# Requires:
#     Python 3.9+

# Result data:
#
# data
# ├── mirrors.json
# ├── versions.json
# └── <OS>
#     └── <platform>
#         └── <qt-version>.json
#
# mirrors.json
# [<link-to-qt-folder>]
#
# versions.json
# {<OS>: {<platform>: [<qt-version>]}}
#
# <qt-version>.json
# {<arch>: {<archive>: {"rel_path": <rel-path>, <hash-algorithm>: <hash>}}}

import argparse
import html.parser
import os
import os.path
import posixpath
import re
import sys
import urllib.error
import urllib.parse
import xml.etree.ElementTree

import qti_util


def argparse_parse(argv):
    script_dir = os.path.dirname(__file__)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawTextHelpFormatter,
        description="There are 4 modes:\n"
                    "1. get a list of working qt mirrors;\n"
                    "2. get a list of available versions"
                    " per platform per OS;\n"
                    "3. print available versions;\n"
                    "4. get a list of hashes"
                    " for archives of available versions.")
    parser.add_argument(
        "-m", "--mode",
        default="print-versions",
        choices=["mirrors", "versions", "print-versions", "hashes"],
        help="Mode of operation.\n"
             "Default: print-versions")
    parser.add_argument(
        "-u", "--qt-url",
        default="https://download.qt.io",
        help="Qt site which provides the mirror list and hashes.\n"
             "Default: https://download.qt.io")
    parser.add_argument(
        "-d", "--data-dir",
        default=os.path.join(script_dir, "data"),
        help="The folder to store the resulting JSON.\n"
             "Default: <script-dir>/data")
    parser.add_argument(
        "-q", "--qt-version",
        nargs="*",
        default=[""],
        help="In 'print-versions' mode,\n"
             "    OS and platform for which to print versions.\n"
             "    If empty, prints available OSs.\n"
             "    If only OS is specified, prints available platforms.\n"
             "In 'hashes' mode,\n"
             "    if specified, download hashes for this verion only.")
    parser.add_argument(
        "-w", "--async-opts",
        nargs=2,
        default=[5, 5],
        type=float,
        help="In 'mirrors' and 'versions' modes,\n"
             "    async download options:\n"
             "1. number of worker processes;\n"
             "2. delay in seconds between progress prints.\n"
             "Default: 5 5")
    parser.add_argument(
        "-a", "--hash-async-opts",
        nargs=2,
        default=[400, 10],
        type=int,
        help="In 'hashes' mode, async download options:\n"
             "1. number of worker processes;\n"
             "2. delay in seconds between progress prints.\n"
             "Default: 400 10")
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


# Retrieves relative URLs from 'href' of '<a>' elements.
class SubitemsListParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.subitems = []

    @staticmethod
    def subitem_from_URL(raw_URL):
        URL = urllib.parse.urlparse(raw_URL)
        if URL.scheme or URL.netloc:
            return ""
        URL_path = posixpath.normpath(URL.path)
        if "/" in URL_path or URL_path == "." or URL_path == "..":
            return ""
        return URL_path

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr in attrs:
                if attr[0] == "href" and attr[1]:
                    subitem = self.subitem_from_URL(attr[1])
                    if subitem:
                        self.subitems.append(subitem)
                    break


def URL_subitems(URL, req_opts):
    html = qti_util.retrieve_URL_str(URL, req_opts)
    parser = SubitemsListParser()
    parser.feed(html)
    return parser.subitems


# Retrieves full URLs from 'href' of '<a>' elements with 'HTTP' content.
class MirrorListParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.last_href = ""
        self.mirrors = []

    @staticmethod
    def full_URL_from_URL(raw_URL):
        URL = urllib.parse.urlparse(raw_URL)
        if URL.scheme and URL.netloc:
            URL = URL._replace(scheme="https")
            if URL.path:
                norm_path = posixpath.normpath(URL.path)
                if norm_path == "/":
                    norm_path = ""
                URL = URL._replace(path=norm_path)
            return urllib.parse.urlunparse(URL)
        return ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for attr in attrs:
                if attr[0] == "href":
                    self.last_href = self.full_URL_from_URL(attr[1])
                    break

    def handle_endtag(self, tag):
        if tag == "a":
            self.last_href = ""

    def handle_data(self, data):
        if data == "HTTP" and self.last_href:
            self.mirrors.append(self.last_href)
            self.last_href = ""


def get_possible_mirrors(qt_URL, req_opts):
    mirrorlist_URL = f"{qt_URL}/static/mirrorlist"
    html = qti_util.retrieve_URL_str(mirrorlist_URL, req_opts)
    parser = MirrorListParser()
    parser.feed(html)
    return [qt_URL] + parser.mirrors


def _check_mirror(mirror_URL, req_opts):
    expected_OSs = ["windows_x86", "linux_x64", "mac_x64"]
    mirror_URL_qtsdk = f"{mirror_URL}/online/qtsdkrepository"
    try:
        subitem_links = URL_subitems(mirror_URL_qtsdk, req_opts)
    except Exception:
        return False
    return set(expected_OSs) <= set(subitem_links)


def get_mirrors(args):
    possible_mirrors = get_possible_mirrors(args.qt_url, args.req_opts)
    async_args = []
    for possible_mirror in possible_mirrors:
        async_arg = (possible_mirror, args.req_opts)
        async_args.append(async_arg)
    print(f"\nChecking {len(possible_mirrors)} qt mirrors.")
    mirrors_availability = qti_util.pool_apply(_check_mirror,
                                               async_args,
                                               args.async_opts)
    mirrors = list(zip(possible_mirrors, mirrors_availability))
    available_mirrors = []
    unavailable_mirrors = []
    for mirror, mirror_available in mirrors:
        if mirror_available:
            available_mirrors.append(mirror)
        else:
            unavailable_mirrors.append(mirror)
    print("\nAvailable mirrors:")
    qti_util.print_list(available_mirrors)
    print("\nUnavailable mirrors:")
    qti_util.print_list(unavailable_mirrors)
    out_JSON = os.path.join(args.data_dir, "mirrors.json")
    qti_util.dump_JSON(available_mirrors, out_JSON)


def real_versions(possible_versions):
    expected_subversions = ["x86_64", "x86", "armv7", "arm64_v8a", "wasm"]
    versions = []
    for possible_version in possible_versions:
        version_split = re.split(r"[_-]", possible_version, 2)
        qt_str, ver_str, subver_str = qti_util.force_len(version_split, 3)
        if (re.fullmatch(r"qt[0-9]+", qt_str)
                and re.fullmatch(r"[0-9]+", ver_str)
                and (not subver_str or subver_str in expected_subversions)):
            versions.append(possible_version)
    return versions


def _get_OS_platform_versions(OS, platform, platform_URL, req_opts):
    possible_versions = URL_subitems(platform_URL, req_opts)
    OS_platform_versions = real_versions(possible_versions)
    return (OS, platform, OS_platform_versions)


def get_versions(args):
    expected_platforms_by_OS = {
        "windows_x86": ["winrt", "android", "desktop"],
        "linux_x64": ["android", "desktop"],
        "mac_x64": ["android", "desktop", "ios"],
    }
    versions = {OS: {} for OS in expected_platforms_by_OS.keys()}
    sdk_URL = f"{args.qt_url}/online/qtsdkrepository"
    async_args = []
    for OS, platforms in expected_platforms_by_OS.items():
        for platform in platforms:
            platform_URL = f"{sdk_URL}/{OS}/{platform}"
            async_arg = (OS, platform, platform_URL, args.req_opts)
            async_args.append(async_arg)
    print(f"\nFetching available versions from {len(async_args)} HTML pages\n"
          f"    from {sdk_URL}")
    async_results = qti_util.pool_apply(_get_OS_platform_versions,
                                        async_args,
                                        args.async_opts)
    for async_result in async_results:
        OS, platform, OS_platform_versions = async_result
        versions[OS][platform] = OS_platform_versions
    out_JSON = os.path.join(args.data_dir, "versions.json")
    qti_util.dump_JSON(versions, out_JSON)


def print_versions(args):
    OS, platform = qti_util.force_len(args.qt_version, 2)
    versions_file = os.path.join(args.data_dir, "versions.json")
    versions = qti_util.load_JSON(versions_file)
    if OS and platform:
        qti_util.print_list(versions[OS][platform])
    elif OS:
        qti_util.print_list(versions[OS].keys())
    else:
        qti_util.print_list(versions.keys())


def arch_from_pkg_name(pkg_name):
    if "debug_info" in pkg_name:
        return pkg_name[pkg_name.find("debug_info"):]
    else:
        return pkg_name.split(".")[-1]


def shorten_archive_name(archive):
    return re.split(r"-Windows|-Linux|-MacOS", archive)[0]


def _get_archives_of_version(version_URL, req_opts):
    archives_of_version = {}
    updates_xml_URL = f"{version_URL}/Updates.xml"
    updates_xml = qti_util.retrieve_URL_str(updates_xml_URL, req_opts)
    xml_tree = xml.etree.ElementTree.fromstring(updates_xml)
    for package_update in xml_tree.iter("PackageUpdate"):
        pkg_name_tag = package_update.find("Name")
        exact_version_tag = package_update.find("Version")
        archives_tag = package_update.find("DownloadableArchives")
        try:
            pkg_name = pkg_name_tag.text
            exact_version = exact_version_tag.text
            archives_of_pkg = archives_tag.text.split(", ")
        except AttributeError:
            continue
        if pkg_name and exact_version and archives_of_pkg[0]:
            arch = arch_from_pkg_name(pkg_name)
            for archive_of_pkg in archives_of_pkg:
                archive_name = shorten_archive_name(archive_of_pkg)
                rel_path = f"{pkg_name}/{exact_version}{archive_of_pkg}"
                if arch not in archives_of_version:
                    archives_of_version[arch] = {}
                archives_of_version[arch][archive_name] = {
                    "rel_path": rel_path,
                    qti_util.HASH_ALG: "",
                }
    return archives_of_version


def get_archives(sdk_URL, ver_paths, async_opts, req_opts):
    async_args = []
    for ver_path in ver_paths:
        ver_URL = f"{sdk_URL}/{ver_path}"
        async_arg = (ver_URL, req_opts)
        async_args.append(async_arg)
    print("\nGetting the list of available archives"
          " by fetching and processing\n"
          f"    {len(async_args)} 'Updates.xml' files\n"
          f"    from {sdk_URL}")
    archives_as_list = qti_util.pool_apply(_get_archives_of_version,
                                           async_args,
                                           async_opts)
    return dict(zip(ver_paths, archives_as_list))


def fetch_hash(archive_URL, req_opts):
    hash_URL = f"{archive_URL}.{qti_util.HASH_ALG}"
    hash_str = qti_util.retrieve_URL_str(hash_URL, req_opts)
    return hash_str.split()[0]


def _fetch_hash(ver_path, arch, archive_name, archive_URL, req_opts):
    fetched_hash = fetch_hash(archive_URL, req_opts)
    return (ver_path, arch, archive_name, fetched_hash)


def fill_archives_with_hashes(archives, sdk_URL, async_opts, req_opts):
    async_args = []
    for ver_path, archives_of_version in archives.items():
        for arch, archives_of_arch in archives_of_version.items():
            for archive_name, archive_info in archives_of_arch.items():
                archive_rel_path = archive_info['rel_path']
                arc_URL = f"{sdk_URL}/{ver_path}/{archive_rel_path}"
                async_arg = (ver_path, arch, archive_name, arc_URL, req_opts)
                async_args.append(async_arg)
    print(f"\nFetching {len(async_args)} hashes for available archives\n"
          f"    from {sdk_URL}")
    async_results = qti_util.pool_apply(_fetch_hash, async_args, async_opts)
    for async_result in async_results:
        ver_path, arch, archive_name, fetchedhash = async_result
        archives[ver_path][arch][archive_name][qti_util.HASH_ALG] = fetchedhash


def get_hashes(args):
    sdk_URL = f"{args.qt_url}/online/qtsdkrepository"
    ver_paths = []
    OS, platform, version = qti_util.force_len(args.qt_version, 3)
    if OS and platform and version:
        ver_path = f"{OS}/{platform}/{version}"
        single_async_opts = [1, *args.hash_async_opts[1:]]
        archives = get_archives(sdk_URL,
                                [ver_path],
                                single_async_opts,
                                args.req_opts)
    elif OS:
        sys.exit("qt-version - 'platform' or 'version' not specified.")
    else:
        ver_info_JSON = os.path.join(args.data_dir, "versions.json")
        versions = qti_util.load_JSON(ver_info_JSON)
        for OS, versions_of_OS in versions.items():
            for platform, versions_of_platform in versions_of_OS.items():
                for version in versions_of_platform:
                    ver_path = f"{OS}/{platform}/{version}"
                    ver_paths.append(ver_path)
        archives = get_archives(sdk_URL,
                                ver_paths,
                                args.hash_async_opts,
                                args.req_opts)
    fill_archives_with_hashes(archives,
                              sdk_URL,
                              args.hash_async_opts,
                              args.req_opts)
    for ver_path, archives_of_ver_path in archives.items():
        if archives_of_ver_path:
            out_JSON = os.path.join(args.data_dir, f"{ver_path}.json")
            qti_util.dump_JSON(archives_of_ver_path, out_JSON)


def main(args):
    args = argparse_parse(sys.argv)
    if args.mode == "mirrors":
        get_mirrors(args)
    elif args.mode == "versions":
        get_versions(args)
    elif args.mode == "print-versions":
        print_versions(args)
    elif args.mode == "hashes":
        get_hashes(args)


if __name__ == "__main__":
    main(sys.argv)
