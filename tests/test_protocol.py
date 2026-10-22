import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from stock_protocol import *
class Protocol(unittest.TestCase):
    def setUp(self): self.payload=unpack(Path(__file__).with_name('stock-v5-config.bin').read_bytes()); self.baseline=state(self.payload)['baseline']
    def test_preserves_unrelated_bytes(self):
        for effect in range(19):
            after=patch(self.payload,self.baseline,dict(effect=effect,brightness=4,speed=3,palette=7))
            allowed={5,9,10,56+effect*2,57+effect*2}
            self.assertTrue(all(a==b for i,(a,b) in enumerate(zip(after,self.payload)) if i not in allowed))
            self.assertEqual(after[56+effect*2]&224,self.payload[56+effect*2]&224)
            self.assertEqual(state(after)['brightness'],4)
    def test_direct_rgb_packet(self):
        p=direct_packet([0,255,0])
        self.assertEqual(len(p),520)
        self.assertEqual(p[:8],bytes([6,8,0,0,1,0,122,1]))
        self.assertEqual(p[8:386],bytes([0,255,0])*126)
        self.assertEqual(p[386:],bytes(134))
        for bad in ([1,2],[-1,0,0],[0,256,0],[True,0,0],'red'):
            with self.assertRaises(ValueError): direct_packet(bad)
    def test_stale(self):
        with self.assertRaises(ValueError): patch(self.payload,'stale',{'brightness':0})
    def test_invalid(self):
        for change in ({'brightness':5},{'speed':-1},{'palette':True},{'anything':0},{'effect':19}):
            with self.assertRaises(ValueError): patch(self.payload,self.baseline,change)
    def test_reject_bad_reports(self):
        for report in (bytes(520),HEADER+bytes(511),HEADER+bytes(512)):
            with self.assertRaises(ValueError): unpack(report)
    def test_unchanged(self): self.assertEqual(patch(self.payload,self.baseline,{'brightness':state(self.payload)['brightness']}),self.payload)
if __name__=='__main__': unittest.main()
