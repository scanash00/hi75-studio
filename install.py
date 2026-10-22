#!/usr/bin/env python3
import os, json, pwd, shutil, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def copy(name,dest,mode=0o644):
    target=Path(dest)/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target); target.chmod(mode); os.chown(target,0,0)
def main():
    if os.geteuid()!=0: raise SystemExit('Run with pkexec python3 install.py')
    user=pwd.getpwuid(int(os.environ.get('PKEXEC_UID',os.environ.get('SUDO_UID','0')))).pw_name
    if user=='root': raise SystemExit('Run from your regular user account')
    for name in ('control.py','stock_protocol.py','daemon.py','keymap_protocol.py','table_control.py','keymap-layout.json'): copy(name,'/usr/local/lib/hi75-studio')
    for name in ('hi75_gtk.py','keyboard.py','keyboard-layout.json','color_widgets.py','keymap_protocol.py','keymap_ui.py','keymap-layout.json'): copy(name,'/usr/local/share/hi75-studio')
    copy('hi75-studio-control','/usr/local/bin',0o755)
    copy('local.hi75.studio.policy','/usr/share/polkit-1/actions')
    copy('local.hi75.Studio.desktop','/usr/local/share/applications')
    copy('local.hi75.Studio.svg','/usr/local/share/icons/hicolor/scalable/apps')
    rules=Path('/etc/polkit-1/rules.d/49-hi75-studio.rules')
    rules.write_text('polkit.addRule(function(action, subject) { if (action.id === "local.hi75.studio.control" && subject.user === '+json.dumps(user)+' && subject.local && subject.active) return polkit.Result.YES; });\n'); rules.chmod(0o644)
    subprocess.run(['update-desktop-database','/usr/local/share/applications'],check=False)
    copy('hi75-studio-rgb.service','/etc/systemd/system')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    # Onboard persistence is required; do not enable host RGB replay at boot.
    subprocess.run(['systemctl','disable','hi75-studio-rgb.service'],check=True)
    print('HI75 Studio installed for '+user)
if __name__=='__main__': main()
