import json,sys,unittest,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hi75_gtk import Studio
from keymap_protocol import digest,plan_macro
from table_control import result
from gi.repository import GLib
ROOT=Path(__file__).resolve().parents[1]
class EditorsTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.app=Studio(True);cls.app.set_application_id('local.hi75.Studio.EditorTests');cls.app.register(None);cls.app.activate()
 def setUp(self):
  cap=json.loads((ROOT/'research/stock-capabilities/live-tables.json').read_text())
  self.keys=[bytes.fromhex(p) for p in cap['tables']['keymap']];self.raw=bytes.fromhex(''.join(cap['tables']['macros']))
  self.e=self.app.editors;self.e.done(result(self.keys,self.raw),'tables');self.e.pending=None;self.e.error=False;self.app.closing=False
 def tearDown(self):
  if self.e.timer:GLib.source_remove(self.e.timer);self.e.timer=0
  self.e.pending=None
 def test_click_uses_firmware_position(self):
  self.e.clicked(None,13);self.assertEqual(self.e.selected()['position'],78)
  self.e.target.set_selected(1)
  self.assertEqual(self.e.pending[1]['position'],78)
  self.assertFalse(self.e.macrobox.get_sensitive())
 def test_protected_fn_and_knob(self):
  for visual in (84,14):
   self.e.clicked(None,visual);self.assertFalse(self.e.assignment.get_sensitive());self.e.key_changed();self.assertIsNone(self.e.pending)
 def test_macro_creation_and_saved_index(self):
  e=self.e;e.new_macro();self.assertIsNone(e.pending)
  e.add_step();operation,request=e.pending;self.assertEqual(operation,'macro-save')
  raw,index=plan_macro(self.raw,request['baseline'],None,request['name'],request['steps'])
  data=result(self.keys,raw);data['saved_index']=index;e.pending=None;e.done(data,'macro-save')
  self.assertEqual(e.macro_index,index);self.assertEqual(e.steps,request['steps']);self.assertTrue(e.editor.get_visible())
 def test_fn_restore_is_original_not_fallback(self):
  e=self.e;e.layer.set_selected(1);e.clicked(None,2);e.restore_key()
  self.assertEqual(e.pending[1]['action'],{'kind':'original'});self.assertEqual(e.pending[1]['bank'],2)
 def test_failed_save_does_not_close_or_claim_success(self):
  self.app.closing=True;self.e.done({'error':'Write not confirmed'},'remap')
  self.assertFalse(self.app.closing);self.assertIsNone(self.e.data);self.assertTrue(self.app.table_retry.get_visible())
if __name__=='__main__':unittest.main()
