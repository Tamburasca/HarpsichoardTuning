#!/usr/bin/env python

"""
FFTonLiveAudio Copyright (C) 2020-21, Dr. Ralf Antonius Timmermann

A graphical tuning tool for string instruments, such as (1) harpsichords
and (2) pianos.

Collects an audio signal from the input stream, that runs through a FFT.
In the frequency domain peak finding is applied. Of all peaks found, in all
combinations, they are identified as common partials (overtones) to one
fundamental. It is then compared to a tuning table (input value, feel free
to enhance special non-equal tunings yourself) and a given pitch value
(input value). The deviation in units of cent is shown, too low (red),
too high (green).

Inharmonicity of strings is considered by the equation
f_n = n * f_1 * sqrt(1 + B * n**2), where n = 1, 2, 3, ... and
B is the inharmonicity coefficient. The maximum inharmonicity accepted is
defined in parameters.py Change accordingly for harpsichords and pianos.

References:
1) HARVEY FLETCHER, THE JOURNAL OF THE ACOUSTICAL SOCIETY OF AMERICA VOLUME 36,
NUMBER 1 JANUARY 1964
2) HAYE HINRICHSEN, REVISTA BRASILEIRA DE ENSINA FISICA, VOLUME 34, NUMBER 2,
2301 (2012)
3) Joonas Tuovinen, Signal Processing in a Semi-AutomaticPiano Tuning System
(MA of Science), Aalto University, School of Electrical Engineering (2019)

The hotkeys ctrl-y and ctrl-x exits and stops the program, respectively,
ESC to resume. Ctrl-j and ctrl-k shorten and lengthen the recording interval,
whereas ctrl-n and ctrl-m diminish and increase the max frequency displayed.

This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under
certain conditions.
"""

import pyaudio
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.collections import EventCollection
import timeit
import time
from pynput import keyboard
import logging
from operator import itemgetter
from .tuningTable import tuningtable
from .FFTroutines import fft, peak, harmonics
from test import parameters

__author__ = "Dr. Ralf Antonius Timmermann"
__copyright__ = "Copyright (C) Dr. Ralf Antonius Timmermann"
__credits__ = ""
__license__ = "GPLv3"
__version__ = "1.0"
__maintainer__ = "Dr. Ralf A. Timmermann"
__email__ = "rtimmermann@astro.uni-bonn.de"
__status__ = "QA"

print(__doc__)


format = "%(asctime)s.%(msecs)03d %(levelname)s:\t%(message)s"
logging.basicConfig(format=format,
                    level=logging.INFO,
                    datefmt="%H:%M:%S")
if parameters.DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)


class Tuner:

    def __init__(self, tuning, a1):
        """
        :param a1: float
            pitch frequency for a1
        :param tuning: string
            tuning temperament
        """
        self.record_seconds = 2.  # lengths of audio signal chunks in 1st subplot, can be adjusted by hotkey
        self.fmax = 2000.  # maximum frequency display in 2nd subplot, can be adjusted by hotkey
        self.a1 = a1
        self.tuning = tuning  # see tuningTable.py
        self.rc = None

        self.callback_output = []
        audio = pyaudio.PyAudio()
        self.stream = audio.open(format=pyaudio.paInt16,
                                 channels=1,
                                 rate=parameters.RATE,
                                 output=False,
                                 input=True,
                                 stream_callback=self.callback)

    def callback(self, in_data, frame_count, time_info, flag):
        """
        :param in_data:
        :param frame_count:
        :param time_info:
        :param flag:
        :return:
        """
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        self.callback_output.append(audio_data)

        return None, pyaudio.paContinue

    def on_activate_x(self):
        print("continue with ESC")
        self.rc = 'x'

    def on_activate_y(self):
        if self.stream.is_active(): self.stream.stop_stream()
        print("quitting...")
        self.rc = 'y'

    def on_activate_k(self):
        self.record_seconds += 0.1
        if self.record_seconds > 5.0: self.record_seconds = 5.0
        print("Recording Time: {0:1.1f}s".format(self.record_seconds))

    def on_activate_j(self):
        self.record_seconds -= 0.1
        if self.record_seconds < 0.5: self.record_seconds = 0.5
        print("Recording Time: {0:1.1f}s".format(self.record_seconds))

    def on_activate_n(self):
        self.fmax -= 500 if self.fmax > 2000 else 100
        if self.fmax < 500: self.fmax = 500
        print("Max frequency displayed: {0:1.0f}Hz".format(self.fmax))

    def on_activate_m(self):
        self.fmax += 500 if self.fmax >= 2000 else 100
        if self.fmax > 15000: self.fmax = 15000
        print("Max frequency displayed: {0:1.0f}Hz".format(self.fmax))

    def on_activate_esc(self):
        self.rc = 'esc'

    def find(self, f_measured):
        """
        finds key and its offset from true key for given a temperament
        :param f_measured: float
            measured frequency
        :return:
        string
            measured key
        float, None
            offset from true key in cent or None if None found or error
        """
        def timeusage():
            _stop = timeit.default_timer()
            logging.debug("time utilized for key finding [s]: " + str(_stop - _start))

        _start = timeit.default_timer()

        for i in range(-4, 5):  # key range from keys C0 till B8
            offset = np.log2(f_measured / self.a1) * 1200 - i * 1200
            for key, value in tuningtable[self.tuning].items():
                displaced = offset + tuningtable[self.tuning].get('A') - value
                if -60 < displaced < 60:
                    logging.debug(str(i) + " " +
                                  str(key) + " " +
                                  str(value) + " " +
                                  str(displaced + tuningtable[self.tuning].get('A') - value))
                    timeusage()
                    return key, displaced

        timeusage()
        return None, None

    @property
    def animate(self):
        """
        calling routine for audio, FFT, peak and partials and key finding, and plotting. Listens for events in plot
        window

        :return:
        string
            return code
        """
        _firstplot = True
        plt.ion()  # Stop matplotlib windows from blocking

        # start Recording
        self.stream.start_stream()

        while self.stream.is_active():

            _start = timeit.default_timer()
            logging.info('Started Audio Stream ...')

            time.sleep(self.record_seconds)
            self.stream.stop_stream()  # stop the input stream for the time being
            logging.info('Stopped Audio Stream ...')

            # Convert the list of numpy-arrays into a 1D array (column-wise)
            amp = np.hstack(self.callback_output)
            # clear input stream
            self.callback_output = []

            # interrupt on hotkey 'ctrl-x' and resume on 'esc'
            if self.rc == 'x':
                while self.rc != 'esc':  # loop and wait until ESC ist pressed
                    time.sleep(.1)
                self.rc = None
                self.stream.start_stream()
                logging.info('Dump last audio stream ...')
                continue
            elif self.rc == 'y':
                return self.rc

            _stop = timeit.default_timer()
            logging.debug("time utilized for Audio [s]: " + str(_stop - _start))
            logging.info('Analyzing ...')

            samples = len(amp)
            logging.info('Number of samples: ' + str(samples))
            t = np.arange(samples) / parameters.RATE
            resolution = parameters.RATE / samples
            logging.info('Resolution (Hz/channel): ' + str(resolution))

            # calculate FFT
            t1, yfft = fft(amp=amp,
                           samples=samples)
            # peakfinding
            peaks = peak(frequency=t1,
                         spectrum=yfft)
            peakList = list(map(itemgetter(0), peaks))

            if peaks is not None:
                f_measured = harmonics(peaks=peaks)  # find the key

            displayed_text = ""
            color = 'none'
            if len(f_measured) != 0:  # if key is found print it and its offset colored red or green
                tone, displaced = self.find(f_measured=f_measured[0])
                if tone:
                    displayed_text = "{2:s} (a1={3:3.0f}Hz) {0:s} offset={1:.0f} cent"\
                        .format(tone, displaced, self.tuning, self.a1)
                    color = 'green' if displaced >= 0 else 'red'

            _start = timeit.default_timer()
            """
            https://stackoverflow.com/questions/40126176/fast-live-plotting-in-matplotlib-pyplot
            """
            if _firstplot:  # instantiate first plot and copy background
                # Setup figure, axis, lines, text and initiate plot once and copy background
                fig = plt.gcf()
                ax = fig.add_subplot(211)
                ax1 = fig.add_subplot(212)
                fig.set_size_inches(12, 8)
                ln, = ax.plot(t, amp)
                ln1, = ax1.plot(t1, yfft)
                text = ax1.text(self.fmax, np.max(yfft), "",
                                # color='',
                                verticalalignment='top',
                                horizontalalignment='right',
                                fontsize=11,
                                fontweight='bold'
                                )
                ax.set_xlabel('Time/s')
                ax.set_ylabel('Intensity/arb. units')
                ax1.set_xlabel('Frequency/Hz')
                ax1.set_ylabel('Intensity/arb. units')
                axbackground = fig.canvas.copy_from_bbox(ax.bbox)
                ax1background = fig.canvas.copy_from_bbox(ax1.bbox)
            else:
                # upper subplot
                ln.set_xdata(t)
                ln.set_ydata(amp)
                # lower subplot
                ln1.set_xdata(t1)
                ln1.set_ydata(yfft)
            ax.set_xlim([0., np.max(t)])
            ax1.set_xlim([0., self.fmax])
            # set text attributes of lower subplot
            text.set_text(displayed_text)
            text.set_color(color)
            text.set_x(self.fmax)
            text.set_y(np.max(yfft))

            # remove all collections: beginning from last object
            while ax1.collections:
                ax1.collections.pop()
            yevents = EventCollection(positions=peakList,
                                      color='tab:olive',
                                      linelength=0.05*np.max(yfft),
                                      linewidth=2.
                                      )
            ax1.add_collection(yevents)
            yevents1 = EventCollection(positions=f_measured,
                                       color='tab:red',
                                       linelength=0.05*np.max(yfft),
                                       lineoffset=-0.04 * np.max(yfft),
                                       linewidth=2.
                                       )
            ax1.add_collection(yevents1)

            # Rescale the axis so that the data can be seen in the plot
            # if you know the bounds of your data you could just set this once
            # so that the axis don't keep changing
            ax.relim()
            ax.autoscale_view()
            ax1.relim()
            ax1.autoscale_view()
            if _firstplot:
                plt.pause(0.001)
#                fig.canvas.draw()
                _firstplot = False
            else:
                # restore background
                fig.canvas.restore_region(axbackground)
                fig.canvas.restore_region(ax1background)
                # redraw just the points
                ax.draw_artist(ln)
                ax1.draw_artist(ln1)
                ax1.draw_artist(text)
                # fill in the axes rectangle
                fig.canvas.blit(ax.bbox)
                fig.canvas.blit(ax1.bbox)

            fig.canvas.flush_events()
            # resume the audio streaming, expect some retardation for the status change
            self.stream.start_stream()

            _stop = timeit.default_timer()
            logging.debug("time utilized for matplotlib [s]: " + str(_stop - _start))

        return self.rc


def main():

    for tune in tuningtable.keys():
        print("Tuning ({1:d}) {0:s}".format(tune, list(tuningtable).index(tune)))

    a = Tuner(tuning=list(tuningtable.keys())[int(input("Tuning Number?: "))],
              a1=float(input("base frequency for a1 in Hz?: ")))

    h = keyboard.GlobalHotKeys({
        '<ctrl>+x': a.on_activate_x,
        '<ctrl>+y': a.on_activate_y,
        '<ctrl>+j': a.on_activate_j,
        '<ctrl>+k': a.on_activate_k,
        '<ctrl>+m': a.on_activate_m,
        '<ctrl>+n': a.on_activate_n,
        '<esc>': a.on_activate_esc})
    h.start()

    a.animate
    plt.close('all')

    return 0
