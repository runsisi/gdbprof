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
from collections import defaultdict
from time import sleep
import os
import signal

def get_call_chain():
    function_names = []
    frame = gdb.newest_frame()
    while frame is not None:
        function_names.append(frame.name())
        frame = frame.older()

    return tuple(function_names)

class Function:

    def __init__(self, name, indent):
        self.name = name
        self.indent = indent
        self.subfunctions = []

        # count of times we terminated here
        self.count = 0

    def add_count(self):
        self.count += 1

    def get_samples(self):
        _count = self.count
        for function in self.subfunctions:
            _count += function.get_samples()
        return _count

    def get_percent(self, total):
        return 100.0 * self.get_samples() / total

    def get_name(self):
        return self.name;

    def get_func(self, name):
        for function in self.subfunctions:
          if function.get_name() == name:
            return function
        return None

    def get_or_add_func(self, name):
        function = self.get_func(name);
        if function is not None:
            return function; 
        function = Function(name, self.indent)
        self.subfunctions.append(function)
        return function

    def print_samples(self, depth):
#        print("aaaa")
        print("%s%s - %s" % (' ' * (self.indent * depth), self.get_samples(), self.name))
        for function in self.subfunctions:
            function.print_samples(depth+1)

    def print_percent(self, prefix, total):
#        print "%s%0.2f - %s" % (' ' * (self.indent * depth), self.get_percent(total), self.name)
        subfunctions = {}
        for function in self.subfunctions:
            v = function.get_percent(total)
            if function.name is None:
              print(">>>> name = None")
              function.name = "???"
            if v is None:
              print(">>>>%s" % (function.name))
              v = "???"
            subfunctions[function.name] = v
        
        i = 0
        #for name, value in sorted(subfunctions.iteritems(), key=lambda (k,v): (v,k), reverse=True):
        for name, value in sorted(subfunctions.items(), key= lambda kv: (kv[1], kv[0]), reverse=True):
            new_prefix = '' 
            if i + 1 == len(self.subfunctions):
               new_prefix += '  '
            else:
               new_prefix += '| '

            print ("%s%s%0.2f%% %s" % (prefix, "+ ", value, name))

            # Don't descend for very small values
            if value < 0.1:
                continue;

            self.get_func(name).print_percent(prefix + new_prefix, total)
            i += 1

    def add_frame(self, frame):
        if frame is None:
            self.count += 1
        else:
            function = self.get_or_add_func(frame.name())
            function.add_frame(frame.older())

    def inverse_add_frame(self, frame):
        if frame is None:
            self.count += 1
        else:
            function = self.get_or_add_func(frame.name())
            function.inverse_add_frame(frame.newer())

class ProfileCommand(gdb.Command):
    """Wall clock time profiling leveraging gdb for better backtraces."""

    def __init__(self):
        super(ProfileCommand, self).__init__("profile", gdb.COMMAND_RUNNING,
                                             gdb.COMPLETE_NONE, True)

class ProfileBeginCommand(gdb.Command):
    """Profile an application against wall clock time.
profile begin [PERIOD]
PERIOD is the sampling interval in seconds.
The default PERIOD is 0.5 seconds.
    """

    def __init__(self):
        super(ProfileBeginCommand, self).__init__("profile begin",
                                                  gdb.COMMAND_RUNNING)

    def invoke(self, argument, from_tty):
        self.dont_repeat()

        period = 0.1

        args = gdb.string_to_argv(argument)

        if len(args) > 0:
            try:

                period = int(args[0])
            except ValueError:
                print("Invalid number \"%s\"." % args[0])
                return

        def breaking_continue_handler(event):
            sleep(period)
            os.kill(gdb.selected_inferior().pid, signal.SIGINT)

#        call_chain_frequencies = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        top = Function("Top", 2)
        sleeps = 0

        threads = {}
        for i in range(0,2000):
          gdb.events.cont.connect(breaking_continue_handler)
          gdb.execute("continue", to_string=True)
          gdb.events.cont.disconnect(breaking_continue_handler)

          for inf in gdb.inferiors():
            inum = inf.num
            for th in inf.threads():
              thn = th.num
              th.switch()
#              call_chain_frequencies[inum][thn][get_call_chain()] += 1
              frame = gdb.newest_frame()
              while (frame.older() != None):
                frame = frame.older()
#              top.inverse_add_frame(frame);
#              top.add_frame(gdb.newest_frame())
              if thn not in threads:
                threads[thn] = Function(str(thn), 2)
              threads[thn].inverse_add_frame(frame)

          sleeps += 1
          gdb.write(".")
          gdb.flush(gdb.STDOUT)

        print("");
        for thn, function in sorted(threads.items()):
          print("")
          print("Thread: %s" % thn)
          print("")
          function.print_percent("", function.get_samples())
#        top.print_percent("", top.get_samples())

#        print("\nProfiling complete with %d samples." % sleeps)
#        for inum, i_chain_frequencies in sorted(call_chain_frequencies.iteritems()):
#            print ""
#            print "INFERIOR NUM: %s" % inum
#            print ""
#            for thn, t_chain_frequencies in sorted (i_chain_frequencies.iteritems()):
#                print ""
#                print "THREAD NUM: %s" % thn
#                print ""
#
#                for call_chain, frequency in sorted(t_chain_frequencies.iteritems(), key=lambda x: x[1], reverse=True):
#                    print("%d\t%s" % (frequency, '->'.join(str(i) for i in call_chain)))
#
#        for call_chain, frequency in sorted(call_chain_frequencies.iteritems(), key=lambda x: x[1], reverse=True):
#            print("%d\t%s" % (frequency, '->'.join(str(i) for i in call_chain)))


        pid = gdb.selected_inferior().pid
        os.kill(pid, signal.SIGSTOP)  # Make sure the process does nothing until
                                      # it's reattached.
        gdb.execute("detach", to_string=True)
        gdb.execute("attach %d" % pid, to_string=True)
        os.kill(pid, signal.SIGCONT)
        gdb.execute("continue", to_string=True)

ProfileCommand()
ProfileBeginCommand()
