# -*- coding: utf-8 -*-
# Copyright (c) 2012 Mak Nazečić-Andrlon
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import gdb
from time import sleep
import os
import signal

SAMPLE_FREQUENCY = 10
SAMPLE_DURATION = 180


def get_call_chain():
    func_names = []
    frame = gdb.newest_frame()
    while frame is not None:
        func_names.append(frame.name())
        frame = frame.older()

    return tuple(func_names)


class GDBThread:
    def __init__(self, name, num, ptid, func):
        self.name = name
        self.num = num
        self.ptid = ptid
        self.func = func


class GDBFunction:
    def __init__(self, name, indent):
        self.name = name
        self.indent = indent
        self.subfuncs = []

        # count of times we terminated here
        self.count = 0

    def add_count(self):
        self.count += 1

    def get_samples(self):
        _count = self.count
        for func in self.subfuncs:
            _count += func.get_samples()
        return _count

    def get_percent(self, total):
        return 100.0 * self.get_samples() / total

    def get_name(self):
        return self.name

    def get_func(self, name):
        for func in self.subfuncs:
            if func.get_name() == name:
                return func
        return None

    def get_or_add_func(self, name):
        func = self.get_func(name)
        if func is not None:
            return func

        func = GDBFunction(name, self.indent)
        self.subfuncs.append(func)
        return func

    def print_samples(self, depth):
        print("%s%s - %s" % (' ' * (self.indent * depth), self.get_samples(), self.name))
        for func in self.subfuncs:
            func.print_samples(depth + 1)

    def print_percent(self, prefix, total):
        subfuncs = {}
        for func in self.subfuncs:
            v = func.get_percent(total)
            if func.name is None:
                print(">>>> name = None")
                func.name = "???"
            if v is None:
                print(">>>> %s" % func.name)
                v = "???"
            subfuncs[func.name] = v
        
        i = 0
        for name, value in sorted(subfuncs.items(), key= lambda kv: (kv[1], kv[0]), reverse=True):
            new_prefix = '' 
            if i + 1 == len(self.subfuncs):
                new_prefix += '  '
            else:
                new_prefix += '| '

            print("%s%s%0.2f%% %s" % (prefix, "+ ", value, name))

            # Don't descend for very small values
            if value < 0.1:
                continue

            self.get_func(name).print_percent(prefix + new_prefix, total)
            i += 1

    def add_frame(self, frame):
        if frame is None:
            self.count += 1
        else:
            func = self.get_or_add_func(frame.name())
            func.add_frame(frame.older())

    def inverse_add_frame(self, frame):
        if frame is None:
            self.count += 1
        else:
            func = self.get_or_add_func(frame.name())
            func.inverse_add_frame(frame.newer())


class ProfileCommand(gdb.Command):
    """Profile an application against wall clock time.

profile FREQUENCY DURATION
FREQUENCY is the sampling frequency, the default frequency is %dhz.
DURATION is the sampling duration, the default duration is %ds.
    """

    def __init__(self):
        super(ProfileCommand, self).__init__("profile", gdb.COMMAND_RUNNING,
                                             prefix=False)
        self.frequency = SAMPLE_FREQUENCY
        self.duration = SAMPLE_DURATION
        self._period = 1.0 / self.frequency
        self._samples = self.frequency * self.duration

    def complete(self, text, word):
        if word != "":
            return gdb.COMPLETE_NONE

        if text == "":
            return [str(self.frequency)]
        elif len(text.split()) < 2:
            return [str(self.duration)]
        return gdb.COMPLETE_NONE

    def invoke(self, argument, from_tty):
        self.dont_repeat()

        argv = gdb.string_to_argv(argument)

        if len(argv) > 2:
            print("Extraneous argument. Try \"help profile\"")
            return

        if len(argv) > 0:
            try:
                self.frequency = int(argv[0])
                self._period = 1.0 / self.frequency
            except ValueError:
                print("Sample frequency must be an integer. Try \"help profile\".")
                return
        if len(argv) > 1:
            try:
                self.duration = int(argv[1])
                self._samples = self.frequency * self.duration
            except ValueError:
                print("Sample duration must be an integer. Try \"help profile\".")
                return

        gdb.execute("set pagination off")

        def breaking_continue_handler(event):
            sleep(self._period)
            os.kill(gdb.selected_inferior().pid, signal.SIGINT)

        threads = {}
        for i in range(0, self._samples):
            gdb.events.cont.connect(breaking_continue_handler)
            gdb.execute("continue", to_string=True)
            gdb.events.cont.disconnect(breaking_continue_handler)

            for inf in gdb.inferiors():
                for th in inf.threads():
                    th.switch()
                    thn = th.num
                    frame = gdb.newest_frame()
                    while frame.older() is not None:
                        frame = frame.older()
                    if thn not in threads:
                        f = GDBFunction(None, 2)
                        threads[thn] = GDBThread(th.name, thn, th.ptid, f)
                    threads[thn].func.inverse_add_frame(frame)

            gdb.write(".")
            gdb.flush(gdb.STDOUT)

        print("")
        for thn, gdbth in sorted(threads.items()):
            print("")
            print("Thread: %s (%s) - %s samples " % (gdbth.num, gdbth.name, gdbth.func.get_samples()))
            print("")
            gdbth.func.print_percent("", gdbth.func.get_samples())

        pid = gdb.selected_inferior().pid
        os.kill(pid, signal.SIGSTOP)  # Make sure the process does nothing until it's reattached
        gdb.execute("detach", to_string=True)
        gdb.execute("attach %d" % pid, to_string=True)
        os.kill(pid, signal.SIGCONT)
        gdb.execute("continue", to_string=True)


ProfileCommand.__doc__ %= (SAMPLE_FREQUENCY, SAMPLE_DURATION)
ProfileCommand()
