from multiprocessing import Process, Queue
from scipy.optimize import curve_fit
import numpy as np
from operator import itemgetter
import logging
from Tuning import parameters

logging.basicConfig(format=parameters.myformat,
                    level=logging.INFO,
                    datefmt="%H:%M:%S")
if parameters.DEBUG:
    logging.getLogger().setLevel(logging.DEBUG)


class ThreadedOpt(object):
    """
    driver for multiprocessing:
    called by peak finding to locate exacter peak positions through minimizing
    a Gauss fit to each individual peak found. Each minimization call is
    performed by a discrete process (multiprocessing).
    """

    # initializations
    def __init__(self, freq, amp, initial):
        """
        :param freq: list of floats
            frequencies of the FFT
        :param amp:  list of floats
            amplitudes of the FFT
        :param initial: float tuple
            frequencies and corresponding heights of peaks found
        """
        self.__amp = amp
        self.__freq = freq
        self.__num_threads = len(initial)
        self.__x = list(map(itemgetter(0), initial))
        self.__y = list(map(itemgetter(1), initial))

    def run(self):
        """Run the optimization. Make the threads here."""
        queue = Queue()
        processes, peaks = list(), list()
        logging.debug("Number of processes: {0}".format(
            str(self.__num_threads)))

        for thread_id in range(self.__num_threads):
            # Make the threads and start them off
            _process = Process(target=self.fitting,
                               args=(queue, thread_id,))
            processes.append(_process)
            _process.start()

        for _process in processes:
            _process.join(timeout=.05)  # resume after timeout, cleanup later

        while not queue.empty():
            rc = queue.get()
            peaks.append([rc[0], rc[1]])
        queue.close()
        queue.join_thread()

        # clean up processes that did not join within timeout period
        while processes:
            _process = processes.pop()
            if _process.is_alive():
                _process.terminate()
                logging.warning(
                    "Multiprocessing: Process did not join, cleaning up ...")

        return peaks

    def fitting(self, queue, thread_id):
        """
        Each thread goes through this.
        :param queue: object
            common queue
        :param thread_id: int
            thread id = 0, 1, 2, ..., len(initial)-1
        :return: none
        """
        window = parameters.FIT_WINDOW
        x = self.__x[thread_id]
        y = self.__y[thread_id]
        # do not exceed the array on either side
        if x-window < 0 or x+window > len(self.__freq)-1:
            logging.warning('Fit initial value out of range: peak disregarded!')

            return

        # Gaussian width to be guessed better
        guess = [self.__freq[x], y, 2.]
        boundaries = ([self.__freq[x] - window, 0.25*y, 1.],
                      [self.__freq[x] + window, 2*y, 4.])
        try:
            popt_ind, pcov = curve_fit(self.gauss,
                                       self.__freq[x-window:x+window],
                                       self.__amp[x-window:x+window],
                                       p0=guess,
                                       bounds=boundaries,
                                       method='dogbox')
            logging.debug(
                "Position (Hz): {0:e}, "
                "Height (arb. Units): {1:e}, "
                "FWHM (Hz): {2:e}"
                .format(popt_ind[0], popt_ind[1], 2.354 * popt_ind[2]))
        except RuntimeError:
            logging.warning('Fit failure: peak disregarded!')

            return
        # put the results into the queue
        queue.put(popt_ind)

        return

    @staticmethod
    def gauss(x, *params):
        """
        superposition of multi-Gaussian curves on FFT
        :param x: list of floats
            x-values
        :param params:
            param[0]: x-value
            param[1]: amplitude
            param[2]: width
            param[0+i]: x-value
            ...
            where i = 0, 1, 2, ...
        :return:
            y-values of multiple Gaussing fit
        """
        y = np.zeros_like(x)
        for i in range(0, len(params), 3):
            ctr = params[i]
            amp = params[i + 1]
            wid = params[i + 2]
            y = y + amp * np.exp(-0.5 * ((x - ctr) / wid) ** 2)

        return y
