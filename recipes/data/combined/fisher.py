from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
from multiprocessing import Pool
import re

import numpy
from tqdm import tqdm
from utils import remove_punct, convert_to_flac
from functools import partial
from glob import glob
from pydub import AudioSegment
import subprocess

alpha = re.compile(r"^[a-zA-Z\s]+$") 
max_duration = 10 * 1000
test_every = 5

def cure_text(text):
    text = remove_punct(text)
    text = text.lower()
    return " ".join(map(lambda x: x.strip(), text.split(" ")))

def read_dialogs(lines):
    dialogs = []
    for line in lines:
        chunks = line.split()
        if len(chunks) > 0 and not line.startswith("#"):  
            text = cure_text(" ".join(chunks[3:]))
            start_seconds = float(chunks[0]) * 1000
            end_seconds = float(chunks[1]) * 1000
            channel = 1
            if chunks[2] == "B:":
                channel = 2
            start = float(start_seconds)
            end = float(end_seconds)
            dialogs.append((text, start, end, channel))

    return dialogs

def fisher_to_list(audio_path, fisher_path, sph2pipe, txt_file):
    with open(txt_file, "r") as f:
        dialogs = read_dialogs(f.readlines())
        scenario = os.path.dirname(txt_file).split("/")[-1]
        name = os.path.basename(txt_file).split(".")[0]
        export_dir = f"{audio_path}/fisher/{scenario}"
        sph_file = f"{fisher_path}/audio/{scenario}/{name}.sph"
        for channel in ["1", "2"]:
            wav_file = f"{fisher_path}/audio/{scenario}/{name}_c{channel}.wav"
            subprocess.check_call([sph2pipe, "-c", channel, "-p", "-f", "rif", sph_file, wav_file])

        lists = []
        for i, (text, start, end, channel) in enumerate(dialogs):
            if len(text) > 1 and alpha.match(text):
                lst_record = convert_to_flac(f"{fisher_path}/audio/{scenario}/{name}_c{channel}.wav",
                                            start, end, f"{name}_{i}", export_dir, text)
                lists.append(lst_record)
        for channel in ["1", "2"]:   
            os.remove(f"{fisher_path}/audio/{scenario}/{name}_c{channel}.wav")
        return lists
            

def prepare_fisher(fisher, audio_path, text_path, lists_path, processes, sph2pipe):
    train_file = f"{lists_path}/fisher-train.lst"
    if not os.path.exists(train_file):
        with Pool(processes) as p:
            files = list(glob(f"{fisher}/trans/**/*.txt"))
            to_list = partial(fisher_to_list, audio_path, fisher, sph2pipe)
            samples = list(
                tqdm(
                    p.imap(to_list, files),
                    total=len(files),
                )
            )
        with open(train_file, "w") as list_f:
            for s in samples:
                list_f.writelines(s)

    else:
        print(f"{train_file} exists, doing verify")
        new_list = []
        with open(train_file, "r") as list_f:
            for line in list_f:
                filename = line.split(" ")[1]
                text = " ".join(line.strip().split(" ")[3:])
                params = " ".join(line.strip().split(" ")[:3])
                line = f"{params} {text}\n"
                if not os.path.exists(filename) or len(text) < 2 or not alpha.match(text):
                    print(f"{filename} does not exists or text is empty, text: {text}")
                else:
                    new_list.append(line)
        with open(train_file, "w") as list_f:
            list_f.writelines(new_list)
    
    print("Prepared fisher", flush=True)


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description="Combined Dataset creation.")
    parser.add_argument(
        "--dst",
        help="destination directory where to store data",
        default="./data_dir",
    )
    parser.add_argument(
        "--fisher",
        help="Fisher data location",
        default="./fisher",
    )

    parser.add_argument(
        "-p",
        "--process",
        help="number of process for multiprocessing",
        default=8,
        type=int,
    )

    parser.add_argument(
        "--sph2pipe",
        help="path to sph2pipe executable",
        default="./sph2pipe_v2.5/sph2pipe",
    )

    args=parser.parse_args()

    audio_path=os.path.join(args.dst, "audio")
    text_path=os.path.join(args.dst, "text")
    lists_path=os.path.join(args.dst, "lists")
    os.makedirs(f"{audio_path}/fisher", exist_ok=True)
    os.makedirs(text_path, exist_ok=True)
    os.makedirs(lists_path, exist_ok=True)

    prepare_fisher(args.fisher, audio_path, text_path, lists_path, args.process, args.sph2pipe)

