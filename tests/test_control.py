import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import control
from stock_protocol import unpack,state
class Persistence(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.profile=Path(self.directory.name)/'solid.json'
        self.saved=state(unpack(Path(__file__).with_name('stock-v5-config.bin').read_bytes()))
    def tearDown(self): self.directory.cleanup()
    def test_color_survives_helper_lifetime(self):
        with patch.object(control,'PROFILE',self.profile):
            control.save_profile([12,34,56],self.saved)
            self.assertEqual(control.load_profile(),{'rgb':[12,34,56],'state':self.saved})
            self.assertEqual(self.profile.stat().st_mode&0o777,0o600)
            control.save_profile([65,43,21],self.saved)
            self.assertEqual(control.load_profile()['rgb'],[65,43,21])
            self.assertFalse(self.profile.with_suffix('.tmp').exists())
    def test_color_and_brightness_persist_separately(self):
        request={'rgb':[49,20,2],'base_rgb':[195,82,9],'brightness_percent':25}
        with patch.object(control,'PROFILE',self.profile):
            control.save_profile(request['rgb'],self.saved,control.color_details(request))
            result=control.profile_result(control.load_profile())
            self.assertEqual(result['custom_rgb'],[49,20,2])
            self.assertEqual(result['custom_base_rgb'],[195,82,9])
            self.assertEqual(result['custom_brightness'],25)
            with self.assertRaises(ValueError): control.color_details({**request,'brightness_percent':100})
    def test_invalid_color_does_not_replace_saved_profile(self):
        with patch.object(control,'PROFILE',self.profile):
            control.save_profile([12,34,56],self.saved)
            with self.assertRaises(ValueError): control.save_profile([999,0,0],self.saved)
            self.assertEqual(control.load_profile()['rgb'],[12,34,56])
    def test_saved_profile_does_not_replace_keyboard_read(self):
        payload=unpack(Path(__file__).with_name('stock-v5-config.bin').read_bytes())
        with patch.object(control,'PROFILE',self.profile):
            control.save_profile([12,34,56],self.saved)
            with patch.object(sys,'argv',['control','read']), patch.object(control,'device',return_value='/dev/test'), patch.object(control,'service'), patch.object(control,'read',return_value=payload) as read, patch.object(control.os,'open',return_value=42), patch.object(control.os,'close'), patch.object(control.fcntl,'flock'), patch('builtins.open',unittest.mock.mock_open()), contextlib.redirect_stdout(io.StringIO()) as output:
                control.main()
                read.assert_called_once_with(42)
                result=json.loads(output.getvalue())
                self.assertEqual(result['custom_rgb'],[12,34,56])
                self.assertEqual(result['configuration_source'],'keyboard')
    def test_hardware_change_supersedes_saved_solid(self):
        payload=bytearray(unpack(Path(__file__).with_name('stock-v5-config.bin').read_bytes()));payload[10]=2
        with patch.object(control,'PROFILE',self.profile):
            control.save_profile([12,34,56],self.saved)
            with patch.object(sys,'argv',['control','read']), patch.object(control,'device',return_value='/dev/test'), patch.object(control,'service') as service, patch.object(control,'read',return_value=bytes(payload)), patch.object(control.os,'open',return_value=42), patch.object(control.os,'close'), patch.object(control.fcntl,'flock'), patch('builtins.open',unittest.mock.mock_open()), contextlib.redirect_stdout(io.StringIO()) as output:
                control.main()
                result=json.loads(output.getvalue())
                self.assertEqual(result['effect'],2); self.assertNotIn('custom_rgb',result)
                service.assert_called_once_with('stop'); self.assertFalse(self.profile.exists())
