import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from keymap_protocol import *
import table_control as tc
ROOT=Path(__file__).resolve().parents[1]
class Protocol(unittest.TestCase):
 def test_geometry_matches_whitelist(self):
  layout=json.loads((ROOT/'keymap-layout.json').read_text())
  self.assertEqual({k['position'] for k in layout},POSITIONS)
  self.assertEqual(len(layout),len(POSITIONS))
 def test_single_key_edit_preserves_page(self):
  page=bytes((i%256 for i in range(512)))
  result=patch_key(page,digest(page),78,{'kind':'keyboard','usage':104,'modifiers':3},{},0)
  self.assertEqual(result[:312],page[:312]);self.assertEqual(result[316:],page[316:]);self.assertEqual(result[312:316],bytes([0,3,0,104]))
  for position in (59,84,126,-1):
   with self.assertRaises(ValueError):patch_key(page,digest(page),position,{'kind':'keyboard','usage':4},{},0)
  with self.assertRaises(ValueError):patch_key(page,'stale',78,{'kind':'keyboard','usage':4},{},0)
 def test_macro_roundtrip_and_copy_on_write(self):
  data=bytes(4096);steps=[{'usage':6,'modifiers':3,'delay':32767},{'usage':4,'modifiers':0,'delay':1}]
  first,index=plan_macro(data,digest(data),None,'Copy',steps)
  m=parse_macros(first)[index];self.assertEqual(decode_steps(m['events']),steps)
  second,_=plan_macro(first,digest(first),index,'Copy again',steps)
  n=parse_macros(second)[index];self.assertNotEqual(n['offset'],m['offset'])
  self.assertEqual(first[m['offset']:m['offset']+m['length']],second[m['offset']:m['offset']+m['length']])
  self.assertEqual(decode_steps(n['events']),steps)
 def test_macro_rejects_unbounded_delays_and_storage(self):
  for delay in (0,32768,-1,True):
   with self.assertRaises(ValueError):encode_macro('X',[{'usage':4,'delay':delay}])
  bad=bytearray(4096);bad[:4]=bytes([4,0,5,0])
  with self.assertRaises(ValueError):parse_macros(bad)
 def test_delete_refuses_referenced_macro(self):
  data,index=plan_macro(bytes(4096),digest(bytes(4096)),None,'One',[{'usage':4,'delay':100}])
  page=bytearray(512);page[:4]=bytes([3,1,1,index])
  with self.assertRaises(ValueError):plan_delete(data,digest(data),index,[bytes(page)])
  after=plan_delete(data,digest(data),index,[bytes(512)])
  self.assertEqual(parse_macros(after),{})
  self.assertEqual(after[1024:],data[1024:])
 def test_allocator_preserves_unknown_events(self):
  data,index=plan_macro(bytes(4096),digest(bytes(4096)),None,'Other',[{'usage':4,'delay':100}])
  m=parse_macros(data)[index];data=bytearray(data);data[m['offset']+1+len('Other')]=0x70;data=bytes(data)
  self.assertIsNone(decode_steps(parse_macros(data)[index]['events']))
  with self.assertRaises(ValueError):plan_macro(data,digest(data),index,'Edit',[{'usage':4,'delay':100}])
  second,new=plan_macro(data,digest(data),None,'New',[{'usage':5,'delay':100}])
  self.assertEqual(second[m['offset']:m['offset']+m['length']],data[m['offset']:m['offset']+m['length']])
class Transport(unittest.TestCase):
 def test_read_rejects_wrong_headers_and_short_reports(self):
  header=bytes([6,0x83,1,0,1,0,0,2]); replies=iter([bytes(520),header,header+bytes(512)])
  def feature(fd,packet,read=False):return next(replies) if read else packet
  with patch.object(tc.time,'sleep'):self.assertEqual(tc.page_read(1,0x83,2,feature),bytes(512))
 def test_uncertain_write_is_verified_not_repeated(self):
  writes=[];page=bytes([5])*512
  def feature(fd,packet,read=False):
   if packet[1]==3:writes.append(packet);raise OSError(71,'Protocol error')
  with patch.object(tc.time,'sleep'),patch.object(tc,'stable_page',return_value=page):tc.write_page(1,3,0,page,feature)
  self.assertEqual(len(writes),1)
  with patch.object(tc.time,'sleep'),patch.object(tc,'stable_page',return_value=bytes(512)):
   with self.assertRaises(RuntimeError):tc.write_page(1,3,0,page,feature)
  self.assertEqual(len(writes),2)
 def test_payload_commits_before_directory(self):
  keys=[bytes(512)]*8;data=bytes(4096);writes=[]
  with patch.object(tc,'snapshot',return_value=(keys,data)),patch.object(tc,'backup'),patch.object(tc,'write_page',side_effect=lambda fd,cmd,n,p,f:writes.append(n)):
   tc.run(1,'macro-save',{'baseline':digest(data),'index':None,'name':'Test','steps':[{'usage':4,'delay':100}]},None)
  self.assertEqual(writes,[2,0])
if __name__=='__main__':unittest.main()
