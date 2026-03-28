import faulthandler, sys, threading, time, tkinter as tk
import jarvis
faulthandler.enable()
faulthandler.dump_traceback_later(8, repeat=False)
print('creating', flush=True)
root = tk.Tk()
app = jarvis.JarvisApp(root)
print('created', flush=True)
root.after(1200, lambda: (print('quit_app', flush=True), app.quit_app()))
start = time.time()
try:
    root.mainloop()
    print('mainloop_returned', round(time.time() - start, 2), flush=True)
except BaseException as exc:
    print('exception', type(exc).__name__, exc, flush=True)
    raise
finally:
    print('finally_threads', [(t.name, t.daemon) for t in threading.enumerate()], flush=True)
