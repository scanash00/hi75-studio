import sys,unittest
from pathlib import Path
from unittest.mock import patch,mock_open
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import daemon
class Stop(BaseException): pass
class Reconnect(unittest.TestCase):
    def test_disconnect_reopens_device_and_replays_saved_color(self):
        with patch('builtins.open',mock_open()), patch.object(daemon.fcntl,'flock'), patch.object(daemon,'load_profile',return_value={'rgb':[12,34,56]}), patch.object(daemon,'device',side_effect=['/dev/hidraw6','/dev/hidraw9']) as discover, patch.object(daemon.os,'open',side_effect=[41,42]) as opened, patch.object(daemon.os,'close') as closed, patch.object(daemon,'feature',side_effect=[OSError('disconnected'),None]) as feature, patch.object(daemon.time,'sleep',side_effect=[None,Stop()]):
            with self.assertRaises(Stop): daemon.run()
            self.assertEqual(discover.call_count,2)
            self.assertEqual(opened.call_count,2)
            self.assertEqual(feature.call_args_list[0].args[1],feature.call_args_list[1].args[1])
            self.assertEqual([x.args[0] for x in closed.call_args_list],[41,42])
