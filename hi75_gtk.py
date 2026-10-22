#!/usr/bin/env python3
import os
os.environ.setdefault('GSK_RENDERER','cairo')
import gi
gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')
from gi.repository import Gtk, Adw, GLib, Gdk
import json, subprocess, threading, time, colorsys, select
from pathlib import Path
from keyboard import Keyboard
from color_widgets import ColorPlane
# Native IDs are not dropdown positions. See research/effect-names.md.
# 19 is the UI's static-rainbow alias for native effect 1, palette 7.
EFFECTS = (
    (0, 'Off'), (1, 'Solid'), (2, 'Breathing'), (3, 'Color cycle'),
    (4, 'Reactive horizontal wave'), (5, 'Falling rain'), (6, 'Split wave'),
    (7, 'Reactive ripple'), (8, 'Twinkling stars'), (10, 'Snake trail'),
    (11, 'Horizontal wave'), (12, 'Reactive fade'), (13, 'Alternating ripples'),
    (15, 'Per-key color cycle'), (16, 'Vertical wave'), (17, 'Radial wave'),
    (19, 'Static rainbow'),
)
EFFECT_IDS = tuple(effect for effect, _ in EFFECTS)

class Studio(Adw.Application):
    def __init__(self,demo=False):
        settings=Gtk.Settings.get_default()
        if settings: settings.set_property('gtk-application-prefer-dark-theme',False)
        super().__init__(application_id='local.hi75.Studio')
        self.demo=demo; self.current=None; self.pending={}; self.busy=False; self.loading=False; self.edited=0; self.dragging=0; self.closing=False; self.last_error=None; self.custom_rgb=None; self.custom_baseline=None
        self.connect('activate',self.activate)
    def activate(self,*_):
        if hasattr(self,'window'): self.window.present(); return
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.PREFER_DARK)
        self.window=Adw.ApplicationWindow(application=self,title='HI75 Studio',default_width=760,default_height=740)
        self.window.set_size_request(360,500); self.window.connect('close-request',self.close)
        # Observe raw events before child gestures claim slider drags. GestureClick
        # can stop recognizing a click without delivering its released signal.
        pointer=Gtk.EventControllerLegacy()
        pointer.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        pointer.connect('event',self.pointer_event)
        self.window.add_controller(pointer)
        self.window.connect('notify::is-active',self.window_active)
        toolbar=Adw.ToolbarView(); self.window.set_content(toolbar)
        header=Adw.HeaderBar(); toolbar.add_top_bar(header)
        title=Adw.WindowTitle(title='HI75 Studio',subtitle='Stock firmware'); header.set_title_widget(title)
        self.pages=Adw.ViewStack(); toolbar.set_content(self.pages)
        switcher=Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE,stack=self.pages);header.set_title_widget(switcher)
        self.table_retry=Gtk.Button(icon_name='view-refresh-symbolic',tooltip_text='Read keyboard again');self.table_retry.set_visible(False);header.pack_end(self.table_retry)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER); self.pages.add_titled_with_icon(scroll,'lighting','Lighting','display-brightness-symbolic')
        clamp=Adw.Clamp(maximum_size=760,tightening_threshold=600); scroll.set_child(clamp)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=22,margin_start=24,margin_end=24,margin_top=8,margin_bottom=24); clamp.set_child(box)
        keyboard=Keyboard(); self.keyboard=keyboard; box.append(keyboard)
        breakpoint=Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 520px"))
        breakpoint.add_setter(keyboard,"content-height",160)
        self.status=Gtk.Label(label='Looking for your keyboard…',wrap=True); self.status.add_css_class('dim-label'); box.append(self.status)
        self.lighting_group=group=Adw.PreferencesGroup(title='Lighting',description='Changes are saved automatically to your keyboard.'); box.append(group)
        self.controls={}
        for key,title,values in [('effect','Effect',[name for _,name in EFFECTS]),('palette','Color',[f'Color {i}' for i in range(1,8)]+['Multicolor'])]:
            row=Adw.ComboRow(title=title,model=Gtk.StringList.new(values)); row.connect('notify::selected',lambda widget,prop,k=key:self.changed(k,widget.get_selected())); group.add(row); self.controls[key]=row
        for key,title in [('brightness','Brightness'),('speed','Speed')]:
            row=Adw.ActionRow(title=title)
            slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,4,1); slider.set_digits(0); slider.set_draw_value(False); slider.set_hexpand(True)
            slider.set_size_request(130,-1); slider.set_valign(Gtk.Align.CENTER)
            slider.update_property([Gtk.AccessibleProperty.LABEL],[title])
            slider.connect('value-changed',lambda widget,k=key:self.changed(k,round(widget.get_value())))
            row.add_suffix(slider); self.controls[key]=slider
            value=Gtk.Label(label=''); value.set_width_chars(4); row.add_suffix(value); self.controls[key+'_label']=value
            group.add(row); self.controls[key+'_row']=row
        self.picker=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        self.picker.set_visible(False); box.append(self.picker)
        self.plane=ColorPlane(); self.plane.set_content_height(170)
        self.hue=ColorPlane(hue_only=True)
        for control in (self.plane,self.hue):
            control.set_hsv(.5,1,1); control.connect('color-changed',self.picked); self.picker.append(control)
        self.hex_entry=Adw.EntryRow(title='Hex color')
        self.hex_entry.set_text('#00FFFF'); self.hex_entry.connect('changed',self.hex_changed)
        hex_list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE); hex_list.add_css_class('boxed-list'); hex_list.append(self.hex_entry); self.picker.append(hex_list)
        help=Gtk.Label(label='Color and brightness are saved on this computer. Startup replay is disabled.',wrap=True,xalign=0)
        help.add_css_class('caption'); help.add_css_class('dim-label'); self.picker.append(help)
        note=Gtk.Label(label='',wrap=True,xalign=0); note.add_css_class('dim-label'); note.add_css_class('caption'); box.append(note); self.preset_note=note
        from keymap_ui import Editors
        self.editors=Editors(self)
        breakpoint.add_setter(self.editors.keyboard,'content-height',150)
        breakpoint.add_setter(switcher,'policy',Adw.ViewSwitcherPolicy.NARROW)
        self.window.add_breakpoint(breakpoint)
        self.pages.add_titled_with_icon(self.editors.keys_page,'keys','Keys','input-keyboard-symbolic')
        self.pages.add_titled_with_icon(self.editors.macros_page,'macros','Macros','view-list-symbolic')
        self.pages.connect('notify::visible-child-name',self.tab_changed)
        self.table_retry.connect('clicked',lambda *_:self.editors.load())
        self.sensitive(False); self.window.present()
        GLib.timeout_add(200,self.tick); self.poll_due=0; self.tick()
    def tab_changed(self,*_):
        if self.pages.get_visible_child_name()!='lighting' and not self.editors.data:
            self.editors.load()
    def sensitive(self,on):
        for key in ('effect','palette','brightness','speed'): self.controls[key].set_sensitive(on)
    def pointer_event(self,controller,event):
        if event is None: return False
        kind=event.get_event_type()
        if kind==Gdk.EventType.BUTTON_PRESS and event.get_button()==1:
            self.dragging=True
        elif kind==Gdk.EventType.TOUCH_BEGIN:
            self.dragging=True
        elif kind in (Gdk.EventType.BUTTON_RELEASE,Gdk.EventType.TOUCH_END,
                      Gdk.EventType.TOUCH_CANCEL,Gdk.EventType.GRAB_BROKEN):
            self.released()
        elif kind==Gdk.EventType.MOTION_NOTIFY and not event.get_modifier_state() & Gdk.ModifierType.BUTTON1_MASK:
            self.released()
        return False
    def window_active(self,window,*_):
        if not window.is_active(): self.released()
    def released(self,*_):
        if self.dragging:
            self.dragging=False; self.edited=time.monotonic()
    def changed(self,key,value):
        if self.loading or not self.current: return
        if key=='effect':
            if value >= len(EFFECT_IDS): return
            value=EFFECT_IDS[value]
            self.pending.clear()
            if value==1:
                self.pending['rgb']=self.picker_rgb()
            elif value==19:
                self.pending.update(effect=1,palette=7)
            else:
                self.pending[key]=value
        elif key=='brightness' and (self.custom_rgb is not None or 'rgb' in self.pending):
            self.pending['rgb']=self.picker_rgb()
        else: self.pending[key]=value
        self.update_mode()
        self.last_error=None; self.edited=time.monotonic(); self.status.set_label('Changes pending…'); self.labels()
    def update_mode(self):
        position=self.controls['effect'].get_selected()
        selected=EFFECT_IDS[position] if position < len(EFFECT_IDS) else None
        custom=selected==1
        self.picker.set_visible(custom)
        self.controls['palette'].set_visible(selected not in (0,1,19))
        self.controls['brightness_row'].set_visible(selected!=0)
        self.controls['speed_row'].set_visible(selected not in (0,1,19))
        reactive=selected in (4,7,12)
        self.preset_note.set_label('Press keys to see this effect.' if reactive else '')
        self.preset_note.set_visible(reactive)
        self.keyboard.set_content_height(160 if self.window.get_width()<=520 else (190 if custom else 280))
        self.lighting_group.set_description(('Colors apply automatically.' if self.custom_rgb is not None or 'rgb' in self.pending else 'Pick a color to replace the current keyboard preset.') if custom else 'Changes are saved automatically to your keyboard.')
        for key in ('palette','brightness','speed'):
            self.controls[key].set_sensitive(bool(self.current and ((custom and key=='brightness') or (self.current['native'] and not custom))))
    def picker_rgb(self):
        return [round(v*255) for v in colorsys.hsv_to_rgb(self.plane.h,self.plane.s,self.plane.v)]
    def picked(self,control):
        if self.loading: return
        h,s,v=(control.h,self.plane.s,self.plane.v) if control==self.hue else (control.h,control.s,control.v)
        self.plane.set_hsv(h,s,v); self.hue.set_hsv(h,s,v)
        rgb=self.picker_rgb(); self.loading=True
        self.hex_entry.set_text('#'+''.join(f'{v:02X}' for v in rgb)); self.loading=False
        self.changed('rgb',rgb)
    def hex_changed(self,entry):
        if self.loading: return
        raw=entry.get_text().strip().lstrip('#')
        if len(raw)!=6 or any(c not in '0123456789abcdefABCDEF' for c in raw):
            entry.add_css_class('error'); return
        entry.remove_css_class('error')
        rgb=[int(raw[i:i+2],16) for i in (0,2,4)]
        hsv=colorsys.rgb_to_hsv(*(v/255 for v in rgb))
        self.plane.set_hsv(*hsv); self.hue.set_hsv(*hsv); self.changed('rgb',rgb)
    def labels(self):
        self.controls['brightness_label'].set_label(f"{round(self.controls['brightness'].get_value())*25}%")
        self.controls['speed_label'].set_label(str(round(self.controls['speed'].get_value())+1))
    def tick(self):
        if self.busy or (hasattr(self,'editors') and (self.editors.busy or self.editors.pending)): return True
        if self.pending and ('rgb' in self.pending or (not self.dragging and time.monotonic()-self.edited>.85)):
            changes=self.pending; self.pending={}
            if 'rgb' in changes:
                percent=round(self.controls['brightness'].get_value())*25
                self.dispatch('frame' if self.custom_rgb is not None else 'color',{'baseline':self.current['baseline'],
                    'rgb':[round(v*percent/100) for v in changes['rgb']],
                    'base_rgb':changes['rgb'],'brightness_percent':percent})
            else: self.dispatch('apply',{'baseline':self.current['baseline'],'changes':changes,'exit_custom':self.custom_rgb is not None})
        elif not self.pending and time.monotonic()>=self.poll_due and not self.closing:
            self.dispatch('read')
        return True
    def dispatch(self,operation,request=None):
        self.busy=True
        if operation in ('apply','color','frame'): self.status.set_label('Applying color…' if operation in ('color','frame') else 'Saving to keyboard…')
        def worker():
            try:
                if self.demo:
                    result=dict(self.current or {'native':True,'effect':1,'brightness':3,'speed':2,'palette':7,'baseline':'demo'})
                    if request:
                        if operation in ('color','frame'): result.update(custom_rgb=request['rgb'],custom_base_rgb=request.get('base_rgb',request['rgb']),custom_brightness=request.get('brightness_percent',100))
                        else:
                            result.pop('custom_rgb',None); result.update(request['changes'])
                else:
                    proc=subprocess.run(['pkexec','/usr/local/bin/hi75-studio-control',operation],input=json.dumps(request or {}),capture_output=True,text=True,timeout=8)
                    try: result=json.loads(proc.stdout)
                    except ValueError: raise RuntimeError(proc.stderr.strip() or 'HI75 helper is not installed')
                GLib.idle_add(self.done,result,operation)
            except Exception as exc:
                GLib.idle_add(self.done,{'error':str(exc)},operation)
        threading.Thread(target=worker,daemon=True).start()
    def done(self,result,operation):
        self.busy=False; self.poll_due=time.monotonic()+3
        if 'error' in result:
            self.last_error=result['error'] if operation in ('apply','color','frame') else self.last_error
            self.custom_rgb=None; self.custom_baseline=None
            self.pending.clear(); self.current=None; self.sensitive(False); self.status.set_label(result['error'])
        else:
            if operation=='frame': result={**self.current,**result}
            if 'custom_rgb' in result:
                self.custom_rgb=result['custom_rgb']; self.custom_baseline=result['baseline']
            else:
                self.custom_rgb=None; self.custom_baseline=None
            self.current=result; self.loading=True; self.sensitive(True)
            if self.custom_rgb is not None and 'rgb' not in self.pending:
                base=result.get('custom_base_rgb',self.custom_rgb)
                hsv=colorsys.rgb_to_hsv(*(v/255 for v in base))
                self.plane.set_hsv(*hsv); self.hue.set_hsv(*hsv)
                self.hex_entry.set_text('#'+''.join(f'{v:02X}' for v in base))
            if result['native'] or self.custom_rgb is not None or 'rgb' in self.pending:
                for key in ('effect','palette','brightness','speed'):
                    value=self.pending.get(key,result.get(key,0)); control=self.controls[key]
                    if key=='brightness' and self.custom_rgb is not None:
                        value=control.get_value() if 'rgb' in self.pending else result.get('custom_brightness',100)/25
                    if key=='effect':
                        if 'effect' not in self.pending and ('rgb' in self.pending or self.custom_rgb is not None): value=1
                        elif value==1 and self.pending.get('palette',result.get('palette',0))==7: value=19
                        names=[name for _,name in EFFECTS]
                        if value in EFFECT_IDS:
                            value=EFFECT_IDS.index(value)
                        else:
                            names.append(f'Unsupported mode · {value}')
                            value=len(EFFECT_IDS)
                        # ComboRow clamps INVALID_LIST_POSITION to its last item.
                        # Use an explicit read-only fallback instead of mislabeling it.
                        if control.get_model().get_n_items()!=len(names) or len(names)>len(EFFECT_IDS):
                            control.set_model(Gtk.StringList.new(names))
                    if key in ('effect','palette'): control.set_selected(value)
                    else: control.set_value(value)
                self.status.set_label(self.last_error or ('Changes pending…' if self.pending else ('Connected · Solid from saved profile' if self.custom_rgb is not None else 'Connected · Read from keyboard')))
            else:
                self.controls['effect'].set_selected(Gtk.INVALID_LIST_POSITION)
                for key in ('palette','brightness','speed'): self.controls[key].set_sensitive(False)
                self.status.set_label('Custom lighting · Select an effect to use stock lighting')
            self.labels(); self.loading=False; self.update_mode()
        if self.closing and not self.pending and not self.editors.busy and not self.editors.pending: self.quit()
        return False
    def close(self,*_):
        if self.editors.busy or self.editors.pending:
            self.closing=True; self.editors.flush(); return True
        if self.busy or self.pending:
            self.closing=True; self.dragging=0; self.edited=0; self.window.set_sensitive(False); return True
        return False
if __name__=='__main__': Studio(demo='--demo' in __import__('sys').argv).run([])
