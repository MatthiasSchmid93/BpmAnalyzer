from PyQt5.QtWidgets import QApplication
import PySimpleGUI as sg
import sys
import tkinter as tk
from time import sleep

sg.theme("Black")
sg.set_options(dpi_awareness=True)


# switch object sizes of the ui for low resolution or high resolution screens
class win_lay:
    in_win_lst = [[25, 27], [50, 27]]
    in_win_win = [[280, 139], [600, 200]]
    main_win_win = [[590, 230], [1150, 435]]
    main_win_txt_bpm = [[10], [40]]
    main_win_txt_bpmind = [[10], [20]]
    main_win_txt_info = [[5], [20]]
    main_win_bar_size = [[52, 3], [86, 5]]
    main_win_bar_pad = [[10, 10], [20, 20]]
    main_win_but_start = [[10], [20]]
    main_win_but_once = [[5], [20]]
    main_win_but_link = [[10], [20]]
    main_win_but_learn = [[5], [20]]
    make_win_txt_setup = [[100, 15], [211, 20]]
    make_win_lstin = [[25, 10], [50, 20]]
    make_win_lstout = [[25, 10], [50, 30]]
    make_win_txt_info = [[5], [20]]
    make_win_but_learn_pad = [[5], [50]]
    make_win_but_learn_size = [[15], [18]]
    make_win_but_exit = [[10], [35]]
    make_win_win = [[300, 185], [600, 360]]


def check_screen_resolution() -> int:
    app = QApplication(sys.argv)
    screen = app.screens()[0]
    dpi = screen.physicalDotsPerInch()
    app.quit()
    if dpi > 150:
        return int(1)
    else:
        return int(0)


def audio_device_selection(audio_devices: list, resolution: int) -> sg.Window:
    layout = [
        [
            sg.Combo(
                audio_devices[0],
                background_color="white",
                text_color="black",
                default_value="Choose Audio Input...",
                key="board",
                enable_events=True,
                readonly=True,
                pad=(
                    win_lay.in_win_lst[resolution][0],
                    win_lay.in_win_lst[resolution][1],
                ),
            )
        ],
        [
            sg.Button(
                key="Next",
                button_text="NEXT",
                border_width=0,
                size=(7, 1),
                disabled=True,
                focus=True,
                pad=(15, 0),
            )
        ],
    ]

    window = sg.Window(
        "Live BPM Analyzer",
        layout,
        no_titlebar=False,
        titlebar_icon="./bpm.png",
        finalize=True,
        size=(win_lay.in_win_win[resolution][0], win_lay.in_win_win[resolution][1]),
        titlebar_text_color="#ffffff",
        use_custom_titlebar=True,
        titlebar_background_color="#000000",
        titlebar_font=("Arial", 12),
    )
    window.set_icon("./bpm.ico")
    return window


def midi_device_selection(
    available_ports_in, available_ports_out, resolution: int
) -> sg.Window:
    layout = [
        [
            sg.Text(
                "MIDI SETUP",
                background_color="blue",
                pad=(
                    win_lay.make_win_txt_setup[resolution][0],
                    win_lay.make_win_txt_setup[resolution][1],
                ),
            )
        ],
        [
            sg.Combo(
                available_ports_in,
                default_value="choose midi input...",
                pad=(
                    win_lay.make_win_lstin[resolution][0],
                    win_lay.make_win_lstin[resolution][1],
                ),
                size=(31, 1),
                background_color="white",
                text_color="black",
                key="midiinput",
                enable_events=True,
                readonly=True,
            )
        ],
        [
            sg.Combo(
                available_ports_out,
                default_value="choose midi output...",
                pad=(
                    win_lay.make_win_lstout[resolution][0],
                    win_lay.make_win_lstout[resolution][1],
                ),
                size=(31, 1),
                background_color="white",
                text_color="black",
                key="midioutput",
                enable_events=True,
                readonly=True,
            )
        ],
        [
            sg.Text(
                key="infomidi",
                pad=(win_lay.make_win_txt_info[resolution][0], 1),
                font=("", 9),
                background_color="blue",
                text_color="black",
            )
        ],
        [
            sg.Button(
                key="learnsendbpm",
                border_width=0,
                disabled=True,
                button_text="LEARN SEND BPM",
                pad=(win_lay.make_win_but_learn_pad[resolution][0], 1),
                size=(win_lay.make_win_but_learn_size[resolution][0], 1),
            ),
            sg.Button(
                key="Exit",
                border_width=0,
                button_text="EXIT",
                pad=(win_lay.make_win_but_exit[resolution][0], 1),
                size=(6, 1),
            ),
        ],
    ]
    return sg.Window(
        "title",
        layout,
        finalize=True,
        no_titlebar=True,
        background_color="blue",
        size=(win_lay.make_win_win[resolution][0], win_lay.make_win_win[resolution][1]),
        grab_anywhere=True,
        titlebar_icon="./bpm.png",
    )


def midi_device_selection_done(resolution: int) -> sg.Window:
    layout = [
        [
            sg.Text(
                "MIDI SETUP DONE",
                background_color="blue",
                pad=(
                    win_lay.make_win_txt_setup[resolution][0],
                    win_lay.make_win_txt_setup[resolution][1],
                ),
            )
        ],
        [
            sg.Button(
                key="Exit",
                border_width=0,
                button_text="OK",
                pad=(win_lay.make_win_but_exit[resolution][0], 1),
                size=(6, 1),
            ),
        ],
    ]
    return sg.Window(
        "title",
        layout,
        no_titlebar=True,
        finalize=True,
        background_color="blue",
        size=(win_lay.make_win_win[resolution][0], win_lay.make_win_win[resolution][1]),
        grab_anywhere=True,
        titlebar_icon="./bpm.png",
    )


def main_window(resolution: int) -> sg.Window:
    layout = [
        [
            sg.Text(
                "***.**",
                key="bpm",
                font=("", 77),
                pad=(win_lay.main_win_txt_bpm[resolution][0], 1),
            ),
            sg.Text(
                "BPM",
                key="bpmindicate",
                font=("", 26),
                text_color="blue",
                pad=(win_lay.main_win_txt_bpmind[resolution][0], 1),
            ),
        ],
        [
            sg.Text(
                key="info",
                pad=(win_lay.main_win_txt_info[resolution][0], 1),
                font=("", 9),
            )
        ],
        [
            sg.ProgressBar(
                150,
                orientation="h",
                size=(
                    win_lay.main_win_bar_size[resolution][0],
                    win_lay.main_win_bar_size[resolution][1],
                ),
                pad=(
                    win_lay.main_win_bar_pad[resolution][0],
                    win_lay.main_win_bar_pad[resolution][1],
                ),
                border_width=0,
                key="-PROGRESS_BAR-",
                bar_color=("Blue", "Blue"),
            )
        ],
        [
            sg.Button(
                key="link",
                button_text="LINK",
                border_width=0,
                size=(7, 1),
                pad=(win_lay.main_win_but_link[resolution][0], 2),
            ),
            sg.Button(
                key="sendbpm",
                button_text="SEND BPM",
                border_width=0,
                size=(11, 1),
                button_color="black on white",
            ),
            sg.Button(
                key="settings",
                button_text="SETTINGS",
                border_width=0,
                pad=(win_lay.main_win_but_learn[resolution][0], 2),
                size=(10, 1),
            ),
        ],
    ]
    return sg.Window(
        "Live BPM Analyzer",
        layout,
        no_titlebar=False,
        finalize=True,
        titlebar_icon="./bpm.png",
        size=(win_lay.main_win_win[resolution][0], win_lay.main_win_win[resolution][1]),
        titlebar_text_color="#ffffff",
        use_custom_titlebar=True,
        titlebar_background_color="#000000",
        titlebar_font=("Arial", 12),
        grab_anywhere=True,
        icon="./bpm.ico",
    )


def update_link_button(main_window: object, modules: object) -> None:
    isOn = 0
    button_info = {
        0: ("LINK", "white on blue"),
        1: ("1 LINK", "white on blue"),
        2: ("2 LINKS", "white on blue"),
        3: ("3 LINKS", "white on blue"),
    }
    while True:
        if main_window == sg.WIN_CLOSED:
            break
        if modules.ableton_link.link.enabled == False:
            break
        peers = (
            modules.ableton_link.num_peers()
            if modules.ableton_link.link.enabled == True
            else peers
        )
        if peers in button_info and peers != isOn:
            main_window.Element("link").Update(
                button_info[peers][0], button_color=button_info[peers][1]
            )
            isOn = peers
        sleep(0.04)
