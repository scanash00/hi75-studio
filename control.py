"""Root helper: only read and validated lighting edits on the known V5 device."""
import fcntl, hashlib, json, os, sys, time, subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from stock_protocol import HEADER, unpack, state, patch, direct_packet
DESCRIPTOR='b67963b7e7759ee51e7766b2c1af46b81577bdf09f10634fa6839ca4a51beb46'
def device():
    for raw in Path('/sys/class/hidraw').glob('hidraw*'):
        d=raw/'device'
        if 'HID_ID=0003:0000258A:0000010C' not in (d/'uevent').read_text(): continue
        if hashlib.sha256((d/'report_descriptor').read_bytes()).hexdigest()!=DESCRIPTOR: continue
        parents=list(d.resolve().parents)
        interface=next((p for p in parents if (p/'bInterfaceNumber').exists()),None)
        usb=next((p for p in parents if (p/'bcdDevice').exists()),None)
        if interface and usb and (interface/'bInterfaceNumber').read_text().strip()=='01' and (usb/'bcdDevice').read_text().strip()=='0500': return '/dev/'+raw.name
    raise RuntimeError('Waiting for HI75 · Connect your stock V5 keyboard')
def feature(fd,packet,read=False):
    buf=bytearray(packet)
    count=fcntl.ioctl(fd,0xC0000000 | (len(buf)<<16) | (ord('H')<<8) | (7 if read else 6),buf,True)
    if read and count != len(buf): raise ValueError("Incomplete keyboard reply")
    return bytes(buf)
def read(fd):
    feature(fd,HEADER+bytes(512)); time.sleep(.05)
    return unpack(feature(fd,bytes([6])+bytes(519),True))
PROFILE=Path('/var/lib/hi75-studio/solid.json')
SERVICE='hi75-studio-rgb.service'
def load_profile():
    try:
        data=json.loads(PROFILE.read_text()); direct_packet(data['rgb']); return data
    except FileNotFoundError: return None

def color_details(request):
    rgb=request['rgb']; direct_packet(rgb)
    base=request.get('base_rgb',rgb); direct_packet(base)
    brightness=request.get('brightness_percent',100)
    if type(brightness) is not int or not 0<=brightness<=100:
        raise ValueError('Invalid brightness')
    if rgb!=[round(v*brightness/100) for v in base]:
        raise ValueError('RGB does not match selected color and brightness')
    return {'base_rgb':base,'brightness_percent':brightness}

def profile_result(profile):
    return {**profile['state'],'custom_rgb':profile['rgb'],
            'custom_base_rgb':profile.get('base_rgb',profile['rgb']),
            'custom_brightness':profile.get('brightness_percent',100)}

def save_profile(rgb,current,details=None):
    direct_packet(rgb)
    PROFILE.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temporary=PROFILE.with_suffix('.tmp')
    with open(temporary,'w') as output:
        os.fchmod(output.fileno(),0o600)
        json.dump({'rgb':rgb,'state':current,**(details or {})},output)
        output.flush(); os.fsync(output.fileno())
    os.replace(temporary,PROFILE)
    directory=os.open(PROFILE.parent,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)

def service(action):
    subprocess.run(['/usr/bin/systemctl',action,SERVICE],check=True,capture_output=True,text=True,timeout=5)

def main():
    if len(sys.argv)!=2 or sys.argv[1] not in ('read','apply','color','frame','tables','remap','macro-save','macro-delete'): raise ValueError('Unknown operation')
    operation=sys.argv[1]
    request=json.loads(sys.stdin.read(16385)) if operation not in ('read','tables') else None
    if operation in ('color','frame'): details=color_details(request)
    with open('/run/lock/hi75-studio.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        path=device()
        profile=load_profile()
        if operation in ('color','frame') and profile:
            save_profile(request['rgb'],profile['state'],details)
            service('start')
            print(json.dumps(profile_result(load_profile()))); return
        if operation=='apply': service('stop')
        fd=None
        try:
            fd=os.open(path,os.O_RDWR|os.O_CLOEXEC)
            if operation in ('tables','remap','macro-save','macro-delete'):
                from table_control import run
                print(json.dumps(run(fd,operation,request,feature))); return
            before=read(fd)
            if operation=='read' and profile:
                if state(before)['baseline']==profile['state']['baseline']:
                    print(json.dumps({**profile_result(profile),**state(before),'color_source':'saved_host_profile','configuration_source':'keyboard'})); return
                # A hardware edit supersedes the host's saved override.
                service('stop'); PROFILE.unlink(missing_ok=True)
            if operation in ('color','frame'):
                if request.get('baseline')!=state(before)['baseline']:
                    raise ValueError('Settings changed on the keyboard. Please adjust again.')
                save_profile(request['rgb'],state(before),details)
                service('start')
                print(json.dumps(profile_result(load_profile()))); return
            if operation=='apply':
                after=patch(before,request['baseline'],request['changes'])
                if after!=before:
                    folder=Path('/var/lib/hi75-studio/backups'); folder.mkdir(parents=True,exist_ok=True,mode=0o700)
                    backup=folder/(str(time.time_ns())+'.bin'); backup.write_bytes(HEADER+before); backup.chmod(0o600)
                    feature(fd,bytes([6,4,0,0,1,0,0,2])+after); time.sleep(.6)
                    actual=read(fd)
                    if actual!=after: raise RuntimeError('Keyboard did not confirm the change. No automatic retry was made.')
                    before=actual
                PROFILE.unlink(missing_ok=True)
            print(json.dumps({**state(before),'configuration_source':'keyboard'}))
        finally:
            if fd is not None: os.close(fd)
            # Failed native edits retain the saved solid profile and resume it.
            if operation=='apply' and PROFILE.exists(): service('start')
if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'error':str(exc)})); sys.exit(1)
