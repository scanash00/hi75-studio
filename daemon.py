"""Maintain saved RGB independently of the GTK window; reconnect automatically."""
import os,sys,time,fcntl
sys.path.insert(0,'/usr/local/lib/hi75-studio')
from control import load_profile,device,feature,direct_packet

def run():
    fd=None
    try:
        while True:
            try:
                profile=load_profile()
                if not profile:
                    if fd is not None: os.close(fd); fd=None
                    time.sleep(.25); continue
                if fd is None: fd=os.open(device(),os.O_RDWR|os.O_CLOEXEC)
                # Keep report 08 out of a configuration request/reply transaction.
                with open('/run/lock/hi75-studio.lock','a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    feature(fd,direct_packet(profile['rgb']))
                time.sleep(.08)
            except (OSError,RuntimeError,ValueError,KeyError):
                if fd is not None: os.close(fd); fd=None
                time.sleep(.5)
    finally:
        if fd is not None: os.close(fd)
if __name__=='__main__': run()
