import sys,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hi75_gtk import Studio, EFFECTS, EFFECT_IDS
from gi.repository import GLib, Gdk
class UI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=Studio(True); cls.app.set_application_id('local.hi75.Studio.Tests'); cls.app.register(None); cls.app.activate(); cls.drain()
    @classmethod
    def drain(cls):
        end=time.monotonic()+.15
        while time.monotonic()<end:
            while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
            time.sleep(.005)
    def test_auto_save_debounce_and_drag(self):
        a=self.app; calls=[]; original=a.dispatch
        a.dispatch=lambda *args:calls.append(args)
        try:
            a.changed('brightness',1); a.changed('brightness',2); a.tick(); self.assertEqual(calls,[])
            a.edited=0; a.dragging=1; a.tick(); self.assertEqual(calls,[])
            a.dragging=0; a.tick(); self.assertEqual(calls[0][1]['changes'],{'brightness':2})
        finally: a.dispatch=original
    def test_pointer_release_unblocks_pending_slider_edit(self):
        class Event:
            def __init__(self,kind): self.kind=kind
            def get_event_type(self): return self.kind
            def get_button(self): return 1
            def get_modifier_state(self): return Gdk.ModifierType(0)
        a=self.app; calls=[]; original=a.dispatch
        a.dispatch=lambda *args:calls.append(args)
        try:
            for ending in (Gdk.EventType.BUTTON_RELEASE,Gdk.EventType.TOUCH_CANCEL,
                           Gdk.EventType.GRAB_BROKEN,Gdk.EventType.MOTION_NOTIFY):
                a.pointer_event(None,Event(Gdk.EventType.BUTTON_PRESS))
                a.changed('brightness',2); a.edited=0; a.tick()
                self.assertFalse(calls)
                # No GestureClick released signal is needed after a claimed drag.
                self.assertFalse(a.pointer_event(None,Event(ending)))
                self.assertFalse(a.dragging)
                a.edited=0; a.tick()
                self.assertEqual(calls.pop()[1]['changes'],{'brightness':2})
        finally: a.dispatch=original
    def test_custom_picker_dispatches_rgb(self):
        a=self.app; calls=[]; original=a.dispatch
        a.dispatch=lambda *args:calls.append(args)
        try:
            a.controls['effect'].set_selected(0)
            a.controls['effect'].set_selected(1)
            a.hex_entry.set_text('#123456')
            a.dragging=False; a.edited=0; a.tick()
            self.assertEqual(calls[0][0],'color')
            self.assertEqual(calls[0][1]['base_rgb'],[18,52,86])
            self.assertEqual(calls[0][1]['rgb'],[round(v*calls[0][1]['brightness_percent']/100) for v in [18,52,86]])
            self.assertFalse(a.controls['palette'].get_sensitive())
        finally:
            a.dispatch=original; a.loading=True; a.controls['effect'].set_selected(1); a.loading=False; a.pending={}
    def test_static_rainbow_maps_to_native_multicolor(self):
        a=self.app; calls=[]; original=a.dispatch
        a.dispatch=lambda *args:calls.append(args)
        try:
            a.controls['effect'].set_selected(0); a.controls['effect'].set_selected(EFFECT_IDS.index(19)); a.dragging=False; a.edited=0; a.tick()
            self.assertEqual(calls[0][0],'apply')
            self.assertEqual(calls[0][1]['changes'],{'effect':1,'palette':7})
            self.assertFalse(a.picker.get_visible())
            self.assertFalse(a.controls['speed_row'].get_visible())
        finally: a.dispatch=original; a.pending={}
    def test_solid_updates_use_frames_and_poll_actual_configuration(self):
        a=self.app; calls=[]; original=a.dispatch
        a.dispatch=lambda *args:calls.append(args)
        saved=(a.custom_rgb,a.custom_baseline)
        try:
            a.custom_rgb=[1,2,3]; a.custom_baseline=a.current['baseline']
            a.pending={}; a.poll_due=0; a.busy=False; a.tick()
            self.assertEqual(calls.pop(),('read',))
            a.pending={'rgb':[4,5,6]}; a.dragging=False; a.edited=0; a.tick()
            self.assertEqual(calls[0][0],'frame')
            self.assertEqual(calls[0][1]['base_rgb'],[4,5,6])
        finally: a.dispatch=original; a.custom_rgb,a.custom_baseline=saved; a.pending={}
    def test_brightness_preserves_selected_hex(self):
        a=self.app; a.pending={}; a.custom_rgb=[195,82,9]
        a.loading=True; a.controls['effect'].set_selected(1); a.hex_entry.set_text('#C35209'); a.loading=False
        a.hex_changed(a.hex_entry)
        calls=[]; original=a.dispatch; a.dispatch=lambda *args:calls.append(args)
        try:
            for level in (0,1,4):
                a.controls['brightness'].set_value(level); a.tick()
                request=calls.pop()[1]
                self.assertEqual(request['base_rgb'],[195,82,9])
                self.assertEqual(request['rgb'],[round(v*level/4) for v in [195,82,9]])
                self.assertEqual(a.hex_entry.get_text(),'#C35209')
            self.assertTrue(a.controls['brightness_row'].get_visible())
            self.assertTrue(a.controls['brightness'].get_sensitive())
        finally: a.dispatch=original; a.custom_rgb=None; a.pending={}
    def test_solid_overrides_unrecognized_native_state(self):
        a=self.app; saved=dict(a.current)
        result={'baseline':'reported-hardware-state','native':False,'effect':0,
                'brightness':31,'speed':15,'palette':15,'custom_rgb':[195,82,9],
                'custom_base_rgb':[195,82,9],'custom_brightness':100}
        try:
            a.pending={}; a.done(result,'read')
            self.assertEqual(a.controls['effect'].get_selected(),1)
            self.assertTrue(a.picker.get_visible())
            self.assertEqual(a.hex_entry.get_text(),'#C35209')
            self.assertEqual(a.controls['brightness'].get_value(),4)
            self.assertTrue(a.controls['brightness'].get_sensitive())
            self.assertFalse(a.pending)
        finally: a.custom_rgb=None; a.custom_baseline=None; a.done(saved,'read')
    def test_effect_ids_survive_removed_menu_entries(self):
        a=self.app; saved=dict(a.current)
        try:
            for position,(native,name) in enumerate(EFFECTS):
                a.pending={}
                state=dict(saved,native=True,effect=1 if native==19 else native,palette=7 if native==19 else 0)
                state.pop('custom_rgb',None)
                a.done(state,'read')
                self.assertEqual(a.controls['effect'].get_selected(),position,name)
                self.assertFalse(a.pending)
                a.changed('effect',position)
                if native==1: self.assertIn('rgb',a.pending)
                else: self.assertEqual(a.pending['effect'],state['effect'],name)
                self.assertEqual(a.preset_note.get_visible(),native in (4,7,12))
            for unsupported in (9,14,18):
                a.pending={}; a.done(dict(state,effect=unsupported),'read')
                row=a.controls['effect']
                self.assertEqual(row.get_selected_item().get_string(),f'Unsupported mode · {unsupported}')
                self.assertFalse(a.pending)
                a.changed('effect',row.get_selected())
                self.assertFalse(a.pending)
        finally: a.pending={}; a.done(saved,'read')
    def test_read_does_not_write(self):
        a=self.app; a.pending={}; before=dict(a.current); a.done(before,'read'); self.assertEqual(a.pending,{})
    def test_failed_write_not_retried(self):
        a=self.app; before=dict(a.current); a.pending={'speed':2}; a.done({'error':'Test failure'},'apply'); self.assertFalse(a.pending); a.done(before,'read'); self.assertEqual(a.status.get_label(),'Test failure')
    @classmethod
    def tearDownClass(cls): cls.app.window.destroy(); cls.app.quit()
