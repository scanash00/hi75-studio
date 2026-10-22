"""Keys and onboard macro editors; all confirmed state comes from the helper."""
import json,subprocess,threading,time
from pathlib import Path
from gi.repository import Gtk,Adw,GLib
from keyboard import Keyboard
from keymap_protocol import KEYS,MODIFIERS,MEDIA,PROTECTED,describe
LAYOUT=json.loads(Path(__file__).with_name('keymap-layout.json').read_text())
KEY_NAMES=['Modifier only']+list(KEYS)
KEY_VALUES=[0]+list(KEYS.values())

def combo(title,values): return Adw.ComboRow(title=title,model=Gtk.StringList.new(values))
def page_box():
    scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
    clamp=Adw.Clamp(maximum_size=760,tightening_threshold=600);scroll.set_child(clamp)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20,margin_start=24,margin_end=24,margin_top=12,margin_bottom=28);clamp.set_child(box)
    return scroll,box

def modifiers(changed):
    flow=Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,column_spacing=12,row_spacing=4,max_children_per_line=4,min_children_per_line=2)
    buttons=[]
    for name in MODIFIERS:
        b=Gtk.CheckButton(label=name);b.connect('toggled',changed);flow.append(b);buttons.append(b)
    return flow,buttons

class Editors:
    def __init__(self,app):
        self.app=app;self.data=None;self.busy=False;self.loading=False;self.pending=None;self.timer=0;self.macro_index=None;self.steps=[];self.draft=False;self.error=False
        self.keys_page,box=page_box();self.keybox=box
        self.keyboard=Keyboard();self.keyboard.interactive=True;self.keyboard.set_content_height(245);box.append(self.keyboard)
        self.keyboard.connect('key-selected',self.clicked)
        self.key_status=Gtk.Label(label='Reading assignments from your keyboard…',wrap=True);self.key_status.add_css_class('dim-label');box.append(self.key_status)
        group=Adw.PreferencesGroup(title='Key assignments',description='Choose a key above. Changes are saved to the keyboard automatically.');box.append(group)
        self.layer=combo('Layer',['Main keys','Fn shortcuts']);group.add(self.layer)
        self.key=combo('Selected key',[x['name'] for x in LAYOUT]);group.add(self.key)
        self.layer.connect('notify::selected',self.selection);self.key.connect('notify::selected',self.selection)
        self.assignment=Adw.PreferencesGroup(title='Assignment');box.append(self.assignment)
        self.kind=combo('Action',['Key or shortcut','Media control','Macro','Use main key','Keyboard function']);self.assignment.add(self.kind)
        self.target=combo('Send key',KEY_NAMES);self.assignment.add(self.target)
        flow,self.mods=modifiers(lambda *_:self.key_changed());self.modrow=Gtk.Label(label='Modifiers',xalign=0);self.modrow.add_css_class('heading')
        self.modflow=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);self.modflow.add_css_class('card')
        content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin_start=12,margin_end=12,margin_top=12,margin_bottom=12)
        content.append(self.modrow);content.append(flow);self.modflow.append(content);box.append(self.modflow)
        self.media=combo('Media action',list(MEDIA));self.assignment.add(self.media)
        self.macro_choice=combo('Run once',[]);self.assignment.add(self.macro_choice)
        self.assignment_note=Gtk.Label(wrap=True,xalign=0);self.assignment_note.add_css_class('dim-label');box.append(self.assignment_note)
        self.restore=Gtk.Button(label='Restore original key',halign=Gtk.Align.START);self.restore.connect('clicked',self.restore_key);box.append(self.restore)
        self.kind.connect('notify::selected',self.kind_changed)
        for row in (self.target,self.media,self.macro_choice):row.connect('notify::selected',lambda *_:self.key_changed())
        self.macros_page,box=page_box();self.macrobox=box
        heading=Gtk.Box(spacing=12);box.append(heading)
        intro=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,hexpand=True);heading.append(intro)
        title=Gtk.Label(label='Onboard macros',xalign=0);title.add_css_class('title-1');intro.append(title)
        subtitle=Gtk.Label(label='A sequence of keystrokes, stored in your keyboard.',xalign=0,wrap=True);subtitle.add_css_class('dim-label');intro.append(subtitle)
        self.new=Gtk.Button(label='New macro',valign=Gtk.Align.CENTER);self.new.add_css_class('suggested-action');self.new.connect('clicked',self.new_macro);heading.append(self.new)
        self.macro_status=Gtk.Label(label='Reading macros…',xalign=0,wrap=True);self.macro_status.add_css_class('dim-label');box.append(self.macro_status)
        self.library=Adw.PreferencesGroup();box.append(self.library)
        self.choose=combo('Macro',[]);self.library.add(self.choose);self.choose.connect('notify::selected',self.choose_macro)
        self.editor=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);box.append(self.editor)
        details=Adw.PreferencesGroup();self.editor.append(details)
        self.name=Adw.EntryRow(title='Name');details.add(self.name);self.name.connect('changed',lambda *_:self.macro_changed())
        self.stepbox=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);self.editor.append(self.stepbox)
        actions=Gtk.Box(spacing=12);self.editor.append(actions)
        self.add=Gtk.Button(label='Add keystroke');self.add.connect('clicked',self.add_step);actions.append(self.add)
        self.delete=Gtk.Button(label='Delete macro');self.delete.add_css_class('destructive-action');self.delete.connect('clicked',self.delete_macro);actions.append(self.delete)
        self.editor.set_visible(False)
        self.keybox.set_sensitive(False);self.new.set_sensitive(False)

    def status(self,text,error=False):
        for label in (self.key_status,self.macro_status):
            label.set_label(text)
            (label.add_css_class if error else label.remove_css_class)('error')
    def load(self):
        if not self.busy and not self.pending:self.send('tables')
    def schedule(self,operation,request):
        if self.loading:return
        self.pending=(operation,request);self.status('Saving automatically…')
        self.keybox.set_sensitive(operation=='remap');self.macrobox.set_sensitive(operation!='remap')
        # Keep the editing context fixed until this change is confirmed.
        for widget in (self.key,self.layer,self.choose,self.new):widget.set_sensitive(False)
        if self.timer:GLib.source_remove(self.timer)
        self.timer=GLib.timeout_add(800,self.flush)
    def cancel_pending(self):
        self.pending=None
        if self.timer:GLib.source_remove(self.timer);self.timer=0
        if not self.busy:
            self.keybox.set_sensitive(bool(self.data));self.macrobox.set_sensitive(bool(self.data))
            for widget in (self.key,self.layer,self.choose,self.new):widget.set_sensitive(True)
    def flush(self):
        if self.busy:return True
        self.timer=0
        if self.pending:
            operation,request=self.pending;self.pending=None;self.send(operation,request)
        return False
    def send(self,operation,request=None):
        self.busy=True;self.error=False
        self.keybox.set_sensitive(False);self.macrobox.set_sensitive(False)
        self.status('Reading from keyboard…' if operation=='tables' else 'Saving to keyboard…')
        def worker():
            try:
                if self.app.demo:
                    from table_control import result
                    capture=json.loads((Path(__file__).parent/'research/stock-capabilities/live-tables.json').read_text())
                    data=result([bytes.fromhex(p) for p in capture['tables']['keymap']],bytes.fromhex(''.join(capture['tables']['macros'])))
                else:
                    p=subprocess.run(['pkexec','/usr/local/bin/hi75-studio-control',operation],input=json.dumps(request or {}),capture_output=True,text=True,timeout=45)
                    try:data=json.loads(p.stdout)
                    except ValueError:raise RuntimeError(p.stderr.strip() or 'Could not read the keyboard')
                GLib.idle_add(self.done,data,operation)
            except Exception as exc:GLib.idle_add(self.done,{'error':str(exc)},operation)
        threading.Thread(target=worker,daemon=True).start()
    def done(self,data,operation):
        self.busy=False
        if 'error' in data:
            self.error=True;self.status(data['error'],True)
            # Retain visible edits, but require a fresh read before another write.
            self.data=None;self.keybox.set_sensitive(False);self.macrobox.set_sensitive(False)
            self.app.table_retry.set_visible(True)
        else:
            self.data=data;self.app.table_retry.set_visible(False)
            self.keybox.set_sensitive(True);self.macrobox.set_sensitive(True)
            for widget in (self.key,self.layer,self.choose,self.new):widget.set_sensitive(True)
            if operation=='macro-save':
                match=next((m for m in data['macros'] if m['index']==data.get('saved_index')),None)
                if match:self.macro_index=match['index']
                self.draft=False
            self.loading=True
            self.macro_ids=[m['index'] for m in data['macros']]
            self.choose.set_model(Gtk.StringList.new([m['name'] for m in data['macros']]))
            self.macro_choice.set_model(Gtk.StringList.new([m['name'] for m in data['macros']]))
            self.library.set_visible(bool(data['macros']))
            if self.macro_index not in self.macro_ids:self.macro_index=self.macro_ids[0] if self.macro_ids else None
            if self.macro_index is not None:self.choose.set_selected(self.macro_ids.index(self.macro_index))
            self.loading=False;self.show_key();self.show_macro()
            self.status('Saved to keyboard' if operation!='tables' else 'Read from keyboard')
            if data['macro_error']:
                self.macro_status.set_label(data['macro_error']);self.new.set_sensitive(False)
            elif not data['macros']:self.macro_status.set_label('No macros yet. Create one, then assign it to a key in Keys.')
            else:self.macro_status.set_label(f"{len(data['macros'])} macro{'s' if len(data['macros'])!=1 else ''} · {data['free_bytes']:,} bytes free · Saved on keyboard")
        if self.app.closing:
            if self.error:self.app.closing=False;self.app.window.set_sensitive(True)
            elif not self.app.busy and not self.app.pending:self.app.quit()
        return False
    def selected(self): return LAYOUT[self.key.get_selected()]
    def bank(self):return 0 if self.layer.get_selected()==0 else 2
    def clicked(self,keyboard,pos):
        if self.busy or self.pending:return
        self.key.set_selected(next(i for i,k in enumerate(LAYOUT) if k['visual']==pos))
    def selection(self,*_):
        if not self.loading:self.show_key()
    def show_key(self):
        if not self.data:return
        self.loading=True;k=self.selected();bank=self.bank()
        self.keyboard.selected=k['visual'];self.keyboard.queue_draw()
        record=bytes.fromhex(self.data['keypages'][bank])[k['position']*4:k['position']*4+4]
        macros={m['index']:m for m in self.data['macros']}
        self.assignment.set_title(f"{k['name']} · {describe(record,macros)}")
        kind=3 if not any(record) and bank==2 else {0:0,2:1,3:2}.get(record[0],4)
        names=['Key or shortcut','Media control','Macro','Use main key' if bank==2 else 'Original key']
        if kind==4:names.append('Keyboard function')
        self.kind.set_model(Gtk.StringList.new(names));self.kind.set_selected(kind)
        self.target.set_selected(KEY_VALUES.index(record[3]) if record[0]==0 and record[3] in KEY_VALUES else 0)
        for i,b in enumerate(self.mods):b.set_active(record[0]==0 and bool(record[1]&(1<<i)))
        if kind==1 and record[2]*256+record[3] in MEDIA.values():self.media.set_selected(list(MEDIA.values()).index(record[2]*256+record[3]))
        if kind==2 and record[3] in self.macro_ids:self.macro_choice.set_selected(self.macro_ids.index(record[3]))
        self.assignment.set_sensitive(k['position'] not in PROTECTED)
        self.restore.set_sensitive(k['position'] not in PROTECTED)
        self.loading=False;self.visibility()
    def visibility(self):
        kind=self.kind.get_selected();protected=self.selected()['position'] in PROTECTED
        self.target.set_visible(kind==0);self.modrow.set_visible(kind==0);self.modflow.set_visible(kind==0);self.modflow.set_sensitive(not protected)
        self.media.set_visible(kind==1);self.macro_choice.set_visible(kind==2)
        text='Fn and the knob keep their keyboard functions.' if protected else 'Create a macro in Macros first.' if kind==2 and not self.macro_ids else 'This keyboard function is preserved. Choose another action to replace it.' if kind==4 else 'Fn shortcuts fall back to the main key when unassigned.' if kind==3 else ''
        self.assignment_note.set_label(text);self.assignment_note.set_visible(bool(text))
    def kind_changed(self,*_):
        self.visibility()
        if not self.loading:
            # Choose usable defaults rather than saving an empty keyboard action.
            if self.kind.get_selected()==0 and self.target.get_selected()==0 and not any(b.get_active() for b in self.mods):
                self.loading=True;self.target.set_selected(1);self.loading=False
            self.key_changed()
    def key_changed(self):
        if self.loading or not self.data:return
        kind=self.kind.get_selected();k=self.selected()
        if k['position'] in PROTECTED:return
        if kind==0:
            usage=KEY_VALUES[self.target.get_selected()];mods=sum(1<<i for i,b in enumerate(self.mods) if b.get_active())
            if not usage and not mods:
                self.cancel_pending();self.key_status.set_label('Choose a key or modifier to save this assignment.');return
            action={'kind':'keyboard','usage':usage,'modifiers':mods}
        elif kind==1:action={'kind':'media','usage':list(MEDIA.values())[self.media.get_selected()]}
        elif kind==2:
            pos=self.macro_choice.get_selected()
            if pos>=len(self.macro_ids):
                self.cancel_pending();return
            action={'kind':'macro','index':self.macro_ids[pos]}
        elif kind==3:
            if self.bank()==0:self.restore_key();return
            action={'kind':'inherit'}
        else:return
        self.schedule('remap',{'bank':self.bank(),'position':k['position'],'action':action,'baseline':self.data['key_baselines'][self.bank()]})
    def restore_key(self,*_):
        k=self.selected();action={'kind':'original'}
        self.schedule('remap',{'bank':self.bank(),'position':k['position'],'action':action,'baseline':self.data['key_baselines'][self.bank()]})
    def new_macro(self,*_):
        self.macro_index=None;self.draft=True;self.steps=[];self.loading=True;self.editor.set_sensitive(True)
        self.name.set_text(f"Macro {len(self.data['macros'])+1}");self.loading=False
        self.editor.set_visible(True);self.delete.set_visible(False);self.render_steps()
        self.macro_status.set_label('Add a keystroke to save this macro.');self.name.grab_focus()
    def choose_macro(self,*_):
        if self.loading or not self.data:return
        pos=self.choose.get_selected()
        if pos<len(self.macro_ids):self.macro_index=self.macro_ids[pos];self.draft=False;self.show_macro()
    def show_macro(self):
        macro=next((m for m in self.data['macros'] if m['index']==self.macro_index),None)
        self.editor.set_visible(macro is not None)
        if not macro:return
        self.loading=True;self.name.set_text(macro['name']);self.steps=[dict(s) for s in (macro['steps'] or [])];self.loading=False
        self.delete.set_visible(True);self.editor.set_sensitive(macro['steps'] is not None)
        self.render_steps()
        if macro['steps'] is None:self.macro_status.set_label('This macro uses events from another editor. It is preserved and can still be assigned to a key.')
    def render_steps(self):
        child=self.stepbox.get_first_child()
        while child:
            following=child.get_next_sibling();self.stepbox.remove(child);child=following
        self.add.set_sensitive(len(self.steps)<64)
        for i,step in enumerate(self.steps):
            group=Adw.PreferencesGroup(title=f'Keystroke {i+1}');self.stepbox.append(group)
            remove=Gtk.Button(icon_name='edit-delete-symbolic',tooltip_text='Remove keystroke');remove.add_css_class('flat');remove.set_sensitive(len(self.steps)>1);remove.connect('clicked',lambda _,n=i:self.remove_step(n));group.set_header_suffix(remove)
            key=combo('Key',list(KEYS));key.set_selected(list(KEYS.values()).index(step['usage']));group.add(key)
            key.connect('notify::selected',lambda row,_,n=i:self.step_changed(n,'usage',list(KEYS.values())[row.get_selected()]))
            pause=Adw.SpinRow.new_with_range(1,32767,10);pause.set_title('Pause after · ms');pause.set_value(step['delay']);group.add(pause)
            pause.connect('notify::value',lambda row,_,n=i:self.step_changed(n,'delay',round(row.get_value())))
            flow,buttons=modifiers(lambda *_:None)
            for bit,button in enumerate(buttons):
                button.set_active(bool(step['modifiers']&(1<<bit)))
                button.connect('toggled',lambda _,n=i,bs=buttons:self.step_changed(n,'modifiers',sum(1<<j for j,b in enumerate(bs) if b.get_active())))
            self.stepbox.append(flow)
    def step_changed(self,index,key,value):
        self.steps[index][key]=value;self.macro_changed()
    def add_step(self,*_):
        self.steps.append({'usage':4,'modifiers':0,'delay':100});self.render_steps();self.macro_changed()
    def remove_step(self,index):
        self.steps.pop(index);self.render_steps();self.macro_changed()
    def macro_changed(self):
        if self.loading or not self.data or not self.steps:return
        name=self.name.get_text().strip()
        if not name or len(name.encode())>80:
            self.cancel_pending();self.name.add_css_class('error');self.macro_status.set_label('Enter a name of 1–80 bytes to save this macro.');return
        self.name.remove_css_class('error')
        self.schedule('macro-save',{'index':self.macro_index,'name':name,'steps':[dict(s) for s in self.steps],'baseline':self.data['macro_baseline']})
    def delete_macro(self,*_):
        dialog=Adw.AlertDialog(heading='Delete this macro?',body='Assigned macros must be removed from their keys first.')
        dialog.add_response('cancel','Cancel');dialog.add_response('delete','Delete');dialog.set_response_appearance('delete',Adw.ResponseAppearance.DESTRUCTIVE);dialog.set_default_response('cancel');dialog.set_close_response('cancel')
        dialog.connect('response',lambda _,response:self.schedule('macro-delete',{'index':self.macro_index,'baseline':self.data['macro_baseline']}) if response=='delete' else None)
        dialog.present(self.app.window)
