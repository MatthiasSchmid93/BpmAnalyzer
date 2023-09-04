import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning)
from threading import Thread
from time import sleep

import link
import numpy as np
import pyaudio
import PySimpleGUI as sg
import rtmidi
from psgtray import SystemTray
from collections import deque
import threading
import struct
import UserInterface
import ExtractBpmPatterns
import re
import json
import os
from scipy import signal

print("----")
print("Live BPM Analyzer Version 2.0")
print("© 2023 Matthias Schmid")
print("----")

FRAME_RATE = int(11025)

try:
    BPM_PATTERN = np.load("bpm_pattern.npy")
    BPM_PATTERN_FINE = np.load("bpm_pattern_fine.npy")
except FileNotFoundError:
    ExtractBpmPatterns.extract(FRAME_RATE)
    BPM_PATTERN = np.load("bpm_pattern.npy")
    BPM_PATTERN_FINE = np.load("bpm_pattern_fine.npy")


class ThreadingEvents:
    def __init__(self):
        self.stop_analyzer = threading.Event()
        self.stop_trigger_set_bpm = threading.Event()
        self.stop_update_link_button = threading.Event()
        self.stop_refresh_main_window = threading.Event()
        self.bpm_updated = threading.Event()

    def stop_threads(self) -> None:
        self.stop_analyzer.set()
        self.stop_trigger_set_bpm.set()
        self.stop_update_link_button.set()
        self.stop_refresh_main_window.set()
        
    def start_update_link_button_thread(main_window: object, modules: object) -> None:
        Thread(
            target=UserInterface.update_link_button,
            args=(main_window, modules),
        ).start()
        
    def start_refresh_main_window_thread(main_window: object, modules: object) -> None:
        Thread(
            target=WindowReader.refresh_main_window,
            args=(main_window, modules),
        ).start()
        
    def start_trigger_set_bpm_thread(modules: object, user_mapping: object) -> None:
        Thread(
            target=modules.midi_interface.trigger_set_bpm,
            args=(modules, user_mapping),
        ).start()
        
    def start_run_analyzer_thread(modules: object) -> None:
        Thread(
            target=BpmAnalyzer.run_analyzer, args=(modules,), daemon=True
        ).start()
        

class BpmStorage:
    def __init__(self):
        self._float = 120.00  # default
        self._str = "***.**"  # default
        self.average_window = deque(maxlen=3)


class AbletonLink:
    def __init__(self):
        self.link = link.Link(120.00)
        self.link.startStopSyncEnabled = True
        self.link.enabled = False

    def enable(self, bool: bool) -> None:
        self.link.enabled = bool

    def num_peers(self) -> int:
        return self.link.numPeers()

    def set_bpm(self, bpm: float) -> None:
        for value in [0.001, -0.001]:
            bpm += value
            s = self.link.captureSessionState()
            link_time = self.link.clock().micros()
            s.setTempo(bpm, link_time)
            self.link.commitSessionState(s)
            sleep(0.03)


class AudioStreamer:
    def __init__(self, frame_rate: int, operating_range_seconds=12):
        self.frame_rate = frame_rate
        self.format = pyaudio.paInt16
        self.chunk = 10240
        self.audio = pyaudio.PyAudio()
        self.signal_buffer = deque(maxlen=int(frame_rate * operating_range_seconds))
        self.operating_range_seconds = operating_range_seconds
        self.buffer_updated = threading.Event()
        self.stream = None

    def audio_callback(self, in_data: bytes, frame_count, time_info, status) -> None:
        num_int16_values = len(in_data) // 2
        signal_buffer_int = struct.unpack(f"<{num_int16_values}h", in_data)
        self.signal_buffer.extend(signal_buffer_int)
        self.buffer_updated.set()
        return (None, pyaudio.paContinue)

    def start_stream(self, input_device_index) -> None:
        self.stream = self.audio.open(
            format=self.format,
            channels=1,
            rate=self.frame_rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=input_device_index,
            stream_callback=self.audio_callback,
            start=False,
        )
        self.stream.start_stream()

    def get_buffer(self) -> np.ndarray:
        self.buffer_updated.wait()
        buffer = np.array(self.signal_buffer, dtype=np.int16)
        self.buffer_updated.clear()
        return buffer

    def stop_stream(self):
        self.stream.stop_stream()
        self.stream.close()
        self.audio.terminate()

    def available_audio_devices(self) -> list:
        devices = []
        indices_of_devices = []
        info = self.audio.get_host_api_info_by_index(0)
        numdevices = info.get("deviceCount")
        for i in range(0, numdevices):
            if (
                self.audio.get_device_info_by_host_api_device_index(0, i).get(
                    "maxInputChannels"
                )
            ) > 0:
                device = self.audio.get_device_info_by_host_api_device_index(0, i).get(
                    "name"
                )
                index_of_device = self.audio.get_device_info_by_host_api_device_index(
                    0, i
                ).get("index")
                devices.append(device)
                indices_of_devices.append(index_of_device)
        return [devices, indices_of_devices]


class BpmAnalyzer:
    def search_beat_events(signal_array: np.ndarray, frame_rate: int) -> np.ndarray:
        step_size = frame_rate // 2
        events = []
        for step_start in range(0, len(signal_array), step_size):
            signal_array_window = signal_array[step_start : step_start + step_size]
            signal_array_window[signal_array_window < signal_array_window.max()] = 0
            signal_array_window[signal_array_window > 0] = 1
            event = np.argmax(signal_array_window) + step_start
            events.append(event)
        return np.array(events, dtype=np.int64)

    def bpm_container(beat_events: np.ndarray, bpm_pattern: np.ndarray, steps: int) -> list[list]:
        bpm_container = [list(np.zeros((1,), dtype=np.int64))for _ in range(beat_events.size * steps)]
        for i, beat_event in enumerate(beat_events):
            found_in_pattern = np.where(np.logical_and(bpm_pattern >= beat_event - 20, bpm_pattern <= beat_event + 20))
            for x, q in enumerate(found_in_pattern[0]):
                bpm_container[i * steps + q].append(found_in_pattern[1][x])
        return bpm_container

    def wrap_bpm_container(bpm_container: list, steps: int) -> list[list]:
        def flatten(input_list: list) -> list:
            return [item for sublist in input_list for item in sublist]

        bpm_container_wrapped = [list(np.zeros((1,), dtype=np.int64)) for _ in range(steps)]
        for i, w in enumerate(bpm_container_wrapped):
            w.extend(flatten(bpm_container[i::steps]))
            w.remove(0)
            bpm_container_wrapped[i] = list(filter(lambda num: num != 0, w))
        return bpm_container_wrapped

    def finalise_bpm_container(bpm_container_wrapped: list, steps: int) -> np.ndarray:
        bpm_container_final = np.zeros((steps, 1), dtype=np.int64)
        for i, w in enumerate(bpm_container_wrapped):
            values, counts = np.unique(w, return_counts=True)
            values = values[counts == counts.max()]
            if values[0] > 0:
                count = np.count_nonzero(w == values[0])
                bpm_container_final[i] = count
        return bpm_container_final

    def get_bpm_wrapped(bpm_container_final: np.ndarray) -> np.ndarray:
        return np.where(bpm_container_final == np.amax(bpm_container_final))

    def check_bpm_wrapped(bpm_wrapped: np.ndarray, bpm_container_final: np.ndarray) -> bool:
        count = np.count_nonzero(bpm_container_final == bpm_wrapped[0][0])
        if count > 1 or bpm_container_final[int(bpm_wrapped[0][0])] < 6:
            return 0
        else:
            return 1

    def get_bpm_pattern_fine_window(bpm_wrapped: np.ndarray) -> int:
        start = int(((bpm_wrapped[0][0] / 4) / 0.05) - 20)
        end = int(start + 40)
        return start, end

    def bpm_wrapped_to_float_str(bpm: np.ndarray, bpm_fine: np.ndarray) -> float:
        bpm_float = round(
            float((((bpm[0][0] / 4) + 100) - 1) + (bpm_fine[0][0] * 0.05)), 2
        )
        bpm_str = format(bpm_float, ".2f")
        return bpm_float, bpm_str

    def search_bpm(signal_array: np.ndarray, frame_rate: int) -> tuple:
        bpm_pattern = BPM_PATTERN
        bpm_pattern_fine = BPM_PATTERN_FINE
        beat_events = BpmAnalyzer.search_beat_events(signal_array, frame_rate)
        for switch_pattern in [240, 40]:
            bpm_container = BpmAnalyzer.bpm_container(
                beat_events, bpm_pattern, switch_pattern
            )
            bpm_container_wrapped = BpmAnalyzer.wrap_bpm_container(
                bpm_container, switch_pattern
            )
            try:
                bpm_container_final = BpmAnalyzer.finalise_bpm_container(
                    bpm_container_wrapped, switch_pattern
                )
            except ValueError:
                return 0
            bpm_wrapped = BpmAnalyzer.get_bpm_wrapped(bpm_container_final)
            if not BpmAnalyzer.check_bpm_wrapped(bpm_wrapped, bpm_container_final):
                return 0
            if switch_pattern == 240:
                start, end = BpmAnalyzer.get_bpm_pattern_fine_window(bpm_wrapped)
                bpm_pattern = bpm_pattern_fine[start:end]
                bpm_wrapped_full_range = bpm_wrapped
            else:
                bpm_wrapped_fine_range = bpm_wrapped
                return BpmAnalyzer.bpm_wrapped_to_float_str(
                    bpm_wrapped_full_range, bpm_wrapped_fine_range
                )

    def run_analyzer(modules: object) -> None:
        while not modules.threading_events.stop_analyzer.is_set():
            buffer = modules.audio_streamer.get_buffer()
            buffer = bandpass_filter(buffer)
            if bpm_float_str := BpmAnalyzer.search_bpm(buffer, FRAME_RATE):
                modules.bpm_storage.average_window.append(bpm_float_str[0])
                bpm_average = round(
                    (
                        sum(modules.bpm_storage.average_window)
                        / len(modules.bpm_storage.average_window)
                    ),
                    2,
                )
                (
                    modules.bpm_storage._float,
                    modules.bpm_storage._str,
                ) = bpm_average, format(bpm_average, ".2f")


class MidiInterface:
    def __init__(self):
        self.midi_in = rtmidi.MidiIn()
        self.midi_out = rtmidi.MidiOut()

    def get_available_devices(self):
        available_devices = {
            "midi_devices_in": [],
            "midi_devices_out": [],
            "midi_devices_in_str": [],
            "midi_devices_out_str": [],
        }
        for midi_device in self.midi_in.get_ports():
            if matches := re.search(r"(.+) ([0-9]+)", midi_device):
                available_devices["midi_devices_in"].append(
                    {matches.group(1): matches.group(2)}
                )
                available_devices["midi_devices_in_str"].append(matches.group(1))
        for midi_device in self.midi_out.get_ports():
            if matches := re.search(r"(.+) ([0-9]+)", midi_device):
                available_devices["midi_devices_out"].append(
                    {matches.group(1): matches.group(2)}
                )
                available_devices["midi_devices_out_str"].append(matches.group(1))
        return available_devices

    def set_in_device(self, choosen_midi_device_in: str, midi_devices: dict[str, list]):
        self.midi_in.close_port()
        for midi_device in midi_devices:
            if choosen_midi_device_in in midi_device:
                try:
                    self.midi_in.open_port(int(midi_device[choosen_midi_device_in]))
                except: pass

    def set_out_device(self, choosen_midi_device_out: str, midi_devices: dict[str, list]):
        self.midi_out.close_port()
        for midi_device in midi_devices:
            if choosen_midi_device_out in midi_device:
                try:
                    self.midi_out.open_port(int(midi_device[choosen_midi_device_out]))
                except: pass

    def learn(self):
        count = 0
        while True:
            sleep(0.2)
            midi_in_msg = self.midi_in.get_message()
            if midi_in_msg == None:
                if count >= 1:
                    if midi_in_msg == None:
                        break
            else:
                count =+ 1
                if count == 1:
                    user_mapping = str(midi_in_msg)
        try:
            return convert_midi_msg(user_mapping)
        except: pass

    def trigger_set_bpm(self, modules: object, user_mapping):
        while not modules.threading_events.stop_trigger_set_bpm.is_set():
            sleep(0.02)
            midi_in_msg = str(self.midi_in.get_message())
            try:
                midi_in_msg = convert_midi_msg(midi_in_msg)
            except: pass
            if midi_in_msg == user_mapping:
                modules.ableton_link.set_bpm(modules.bpm_storage._float)
                
    def close_ports(self):
        self.midi_in.close_port
        self.midi_out.close_port


class WindowReader:
    def audio_device_selection(choose_input_window: object, audio_devices: list) -> int:
        def get_choosen_audio_device(values, audio_devices):
            audio_device = values["board"]
            index_for_device = audio_devices[0].index(audio_device)
            return audio_devices[1][index_for_device]
        
        choose_input_window.un_hide()
        while True:
            event, values = choose_input_window.read()
            if event == sg.WIN_CLOSED:
                break
            if event == "Next":
                break
            if event == "board":
                choosen_audio_device = get_choosen_audio_device(values, audio_devices)
                choose_input_window["Next"].update(disabled=False)
        choose_input_window.hide()
        return choosen_audio_device

    def midi_device_selection(
        modules: object,
        midi_device_selection_window: object,
        midi_devices: dict[str, list],
    ):
        midi_device_selection_window.un_hide()
        set_in = False
        set_out = False
        while True:
            event, values = midi_device_selection_window.read()
            sleep(0.02)
            if event == sg.WIN_CLOSED:
                midi_device_selection_window.close()
                break
            if event == "Exit":
                midi_device_selection_window.close()
                break
            if event == "learnsendbpm":
                midi_device_selection_window.Element("learnsendbpm").Update(
                    button_color="black on white"
                )
                user_mapping = modules.midi_interface.learn()
                midi_device_selection_window.close()
                return user_mapping
            if event == "midiinput":
                choosen_device = values["midiinput"]
                modules.midi_interface.set_in_device(
                    choosen_device, midi_devices["midi_devices_in"]
                )
                set_in = True
                if set_out == True:
                    midi_device_selection_window.Element("learnsendbpm").Update(
                        disabled=False
                    )
            if event == "midioutput":
                choosen_device = values["midioutput"]
                modules.midi_interface.set_out_device(
                    choosen_device, midi_devices["midi_devices_out"]
                )
                set_out = True
                if set_in == True:
                    midi_device_selection_window.Element("learnsendbpm").Update(
                        disabled=False
                    )

    def midi_device_selection_done(midi_device_selection_done_window: object):
        midi_device_selection_done_window.un_hide()
        while True:
            event, _ = midi_device_selection_done_window.read()
            sleep(0.02)
            if event == sg.WIN_CLOSED:
                midi_device_selection_done_window.close()
                break
            if event == "Exit":
                midi_device_selection_done_window.close()
                break

    def main_window(main_window: object, modules: object):
        menu = ["", ["Show Window"]]
        tray = SystemTray(
            menu=menu,
            single_click_events=True,
            window=main_window,
            tooltip="Live BPM Analyzer",
            icon="./bpm_tray.png",
        )
        switch_button = True
        while True:
            event, _ = main_window.read()
            sleep(0.02)
            if event == tray.key:
                main_window.BringToFront()
            if event == sg.WIN_CLOSED:
                modules.threading_events.stop_threads()
                modules.ableton_link.enable(False)
                tray.close()
                main_window.close()
                return 0
            if event == "link":
                switch_button = not switch_button
                main_window.Element("link").Update(
                    ("LINK", "LINK")[switch_button],
                    button_color=(("white on blue", "black on white")[switch_button]),
                )
                if switch_button == True:
                    modules.threading_events.stop_update_link_button.set()
                    modules.ableton_link.enable(False)
                if switch_button == False:
                    modules.ableton_link.enable(True)
                    ThreadingEvents.start_update_link_button_thread(main_window, modules)
            if event == "settings":
                modules.threading_events.stop_threads()
                modules.ableton_link.enable(False)
                tray.close()
                main_window.close()
                return 1
            if event == "sendbpm":
                modules.ableton_link.set_bpm(modules.bpm_storage._float)

    def refresh_main_window(main_window: object, modules: object) -> None:
        while not modules.threading_events.stop_refresh_main_window.is_set():
            sleep(1)
            main_window["bpm"].update(modules.bpm_storage._str)


class OpenWindow:
    def __init__(self):
        self.resolution = UserInterface.check_screen_resolution()

    def audio_device_selection(self, modules: object) -> int:
        audio_devices = modules.audio_streamer.available_audio_devices()
        audio_device_selection_window = UserInterface.audio_device_selection(
            audio_devices, self.resolution
        )
        choosen_audio_device = WindowReader.audio_device_selection(
            audio_device_selection_window, audio_devices
        )
        Settings.save(choosen_audio_device=choosen_audio_device)
        return choosen_audio_device

    def midi_device_selection(self, modules: object) -> str:
        midi_devices = modules.midi_interface.get_available_devices()
        midi_device_selection_window = UserInterface.midi_device_selection(
            midi_devices["midi_devices_in_str"],
            midi_devices["midi_devices_out_str"],
            self.resolution,
        )
        if user_mapping := WindowReader.midi_device_selection(
            modules, midi_device_selection_window, midi_devices
        ):
            midi_device_selection_window_done = (
                UserInterface.midi_device_selection_done(self.resolution)
            )
            WindowReader.midi_device_selection_done(midi_device_selection_window_done)
            Settings.save(user_mapping=user_mapping)
            return user_mapping

    def main_window(self, modules) -> None:
        main_window = UserInterface.main_window(self.resolution)
        ThreadingEvents.start_refresh_main_window_thread(main_window, modules)
        if WindowReader.main_window(main_window, modules):
            return 1
        else:
            return 0


class Settings:
    def check() -> bool:
        try:
            with open("settings.json", "r") as _:
                pass
            return 1
        except:
            content = {"choosen_audio_device": "", "user_mapping": ""}
            with open("settings.json", "w") as settings:
                json.dump(content, settings)
            return 0

    def save(choosen_audio_device=None, user_mapping=None) -> None:
        with open("settings.json", "r") as settings:
            content = json.load(settings)
        if choosen_audio_device is not None:
            content["choosen_audio_device"] = choosen_audio_device
        if user_mapping is not None:
            content["user_mapping"] = user_mapping
        with open("settings.json", "w") as settings:
            json.dump(content, settings)

    def open() -> None:
        settings_lst = []
        with open("settings.json", "r") as settings:
            data = json.load(settings)
            for key, value in data.items():
                settings_lst.append(value)
            return settings_lst


class InitialiseModules:
    def __init__(self):
        self.bpm_storage = BpmStorage()
        self.threading_events = ThreadingEvents()
        self.audio_streamer = AudioStreamer(FRAME_RATE)
        self.ableton_link = AbletonLink()
        self.midi_interface = MidiInterface()
        self.open_window = OpenWindow()
        

def convert_midi_msg(msg) -> str:
        for char in "()[]":
            msg = msg.replace(char, "")
        msg = msg.split(",", -1)
        del msg[3]
        for i, value in enumerate(msg):
            msg[i] = value.strip()
        return msg


def bandpass_filter(audio_signal, lowcut=60.0, highcut=3000.0) -> np.ndarray:
    def butter_bandpass(lowcut, highcut, fs, order=10):
            nyq = 0.5 * fs
            low = lowcut / nyq
            high = highcut / nyq
            b, a = signal.butter(order, [low, high], btype='band')
            return b, a

    def butter_bandpass_filter(data, lowcut, highcut, fs, order=10):
        b, a = butter_bandpass(lowcut, highcut, fs, order=order)
        y = signal.lfilter(b, a, data)
        return y

    def _bandpass_filter(buffer):
        return butter_bandpass_filter(buffer, lowcut, highcut, FRAME_RATE, order=6)
    
    return np.apply_along_axis(_bandpass_filter, 0, audio_signal).astype('int16')


def main() -> None:
    while True:
        modules = InitialiseModules()
        if not Settings.check():
            choosen_audio_device = modules.open_window.audio_device_selection(modules)
            user_mapping = modules.open_window.midi_device_selection(modules)
        else:
            settings = Settings.open()
            choosen_audio_device, user_mapping = int(settings[0]), settings[1]
        modules.audio_streamer.start_stream(choosen_audio_device)
        ThreadingEvents.start_trigger_set_bpm_thread(modules, user_mapping)
        ThreadingEvents.start_run_analyzer_thread(modules)
        if modules.open_window.main_window(modules): # Main loop
            modules.audio_streamer.stop_stream()
            modules.midi_interface.close_ports
            ThreadingEvents.stop_threads
            os.remove("settings.json")
        else:
            modules.audio_streamer.stop_stream()
            modules.midi_interface.close_ports
            ThreadingEvents.stop_threads
            sys.exit()


if __name__ == "__main__":
    main()
