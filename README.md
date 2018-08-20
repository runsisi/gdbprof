gdbprof
=======
A wall clock time-based profiler powered by GDB and its Python API. Heavily
inspired by [poor man's profiler](http://poormansprofiler.org/).

Rationale
---------
If there's something strange in your neighborhood (like X consuming 75% CPU in
`memcpy()` which `perf` can't trace), who you gonna call? `gdb`! Of course, if
you're lazy like me, you don't want to spend too much time hitting
<kbd>Ctrl</kbd>+<kbd>C</kbd>.

Caveats
-------
This is hack layered upon hack upon hack. See the source code if you want to
know how it "works". With the current state of gdb's Python affairs, it's
impossible to do it cleanly, but I think it's slightly better than an
expect-based approach because of the lower latency. **Use with CAUTION!**

Also, I recommend **attaching** to a running process, rather than starting it
from gdb. You'll need to hold down <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop it if
you start it from `gdb`, as you need to interrupt `gdb`, not the process (I need
to handle this better).

Example
-------
```
(gdb) source gdbprof.py
(gdb) help profile
Profile an application against wall clock time.

profile FREQUENCY DURATION THRESHOLD
FREQUENCY is the sampling frequency, the default frequency is 10hz.
DURATION is the sampling duration, the default duration is 180s.
THRESHOLD is the sampling filter threshold, the default threshold is %0.50.

(gdb) profile 10 5 0.5
..................................................

Thread: 1 (ceph-osd) - 50 samples

+ 100.00% main
  + 100.00% AsyncMessenger::wait
    + 100.00% Cond::Wait
      + 100.00% pthread_cond_wait@@GLIBC_2.3.2

Thread: 2 (log) - 50 samples

+ 100.00% clone
  + 100.00% start_thread
    + 100.00% Thread::_entry_func
      + 100.00% Thread::entry_wrapper
        + 100.00% ceph::logging::Log::entry
          + 96.00% pthread_cond_wait@@GLIBC_2.3.2
          | + 6.00% __pthread_mutex_cond_lock
          |   + 6.00% __lll_lock_wait
          + 4.00% __GI___pthread_mutex_unlock
            + 4.00% __pthread_mutex_unlock_usercnt
              + 4.00% __lll_unlock_wake
```
