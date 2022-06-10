#! /usr/bin/env python3

import hashlib
import json
import multiprocessing.pool
import os
import shutil
import signal
import time
import urllib.request


HASH_ALG = "sha256"


class HashMismathError(Exception):
    pass


# https://stackoverflow.com/a/44873382
def compute_hash(file, hash_alg):
    hashlib_obj = hashlib.new(hash_alg)
    bytes_obj = bytearray(128*1024)
    memoryview_obj = memoryview(bytes_obj)
    with open(file, 'rb', buffering=0) as file_obj:
        while bytes_read_num := file_obj.readinto(memoryview_obj):
            hashlib_obj.update(memoryview_obj[:bytes_read_num])
    return hashlib_obj.hexdigest()


def print_list(iterable):
    for item in iterable:
        print(item)


def force_len(list_obj, length, pad=""):
    true_els_list = list(filter(None, list_obj))
    overpadded_list = true_els_list + [pad] * length
    return overpadded_list[:length]


def get_dirs(path):
    dirs = []
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_dir():
                dirs.append(entry.name)
    return dirs


def get_files(path):
    files = []
    with os.scandir(path) as it:
        for entry in it:
            if entry.is_file():
                files.append(entry.name)
    return files


def load_JSON(filepath):
    with open(filepath, "r") as file_obj:
        return json.load(file_obj)


def dump_JSON(data, out_file):
    out_dir = os.path.dirname(out_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    tmp_file = out_file + ".tmp"
    with open(tmp_file, "w") as tmp_file_obj:
        json.dump(data, tmp_file_obj)
    os.replace(tmp_file, out_file)


def retrieve_URL_str(URL, opts):
    return retrieve_URL(URL, "", opts).decode(errors="replace")


def retrieve_URL(URL, filepath, opts):
    timeout_s, attempt_delay_s, attempts = opts
    attempts = int(attempts)
    for attempt in range(attempts):
        try:
            contents = ""
            with urllib.request.urlopen(URL, timeout=timeout_s) as response:
                if filepath:
                    with open(filepath, "wb") as file_obj:
                        shutil.copyfileobj(response, file_obj)
                else:
                    contents = response.read()
            return contents
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(attempt_delay_s)


# https://noswap.com/blog/python-multiprocessing-keyboardinterrupt
def init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def pool_apply(_func, async_args, async_opts):
    check_progress_interval = 0.25
    workers_num, print_delay_s = async_opts
    workers_num = int(workers_num)
    async_results = []
    with multiprocessing.Pool(workers_num, init_worker) as pool:
        tasks = [pool.apply_async(_func, async_a) for async_a in async_args]
        total_tasks = len(tasks)
        ready_tasks = 0
        no_print_s = 0
        while ready_tasks < total_tasks:
            time.sleep(check_progress_interval)
            no_print_s += check_progress_interval
            ready_tasks = 0
            for task in tasks:
                if task.ready():
                    if not task.successful():
                        # Reraise the exception.
                        task.get()
                    ready_tasks += 1
            if no_print_s >= print_delay_s:
                print(f"{ready_tasks}/{total_tasks} tasks done."
                      f" {no_print_s} seconds passed since the last print.")
                no_print_s = 0
        async_results = [task.get() for task in tasks]
        print(f"Completed all {total_tasks} tasks.")
    return async_results
