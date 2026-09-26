"""Offline state/PCM tests of the actual patched Soundd class (no device I/O)."""
import ast
import math
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import wave
from unittest.mock import Mock
import numpy as np

HERE = Path(__file__).parent
class Alerts:
  none = 0
  warningSoft = 1
  warningImmediate = 2
  engage = 3

class TestChime(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    root = Path(self.tmp.name)
    asset = root / 'openpilot/selfdrive/assets/sounds/audio_ready.wav'
    asset.parent.mkdir(parents=True)
    asset.write_bytes((HERE / 'audio_ready.wav').read_bytes())
    self.asset = asset
    self.now = 100.
    ns = {'np': np, 'math': math, 'wave': wave, 'BASEDIR': str(root), 'SAMPLE_RATE': 48000,
          'MIN_VOLUME': .1, 'FILTER_DT': .1, 'AudibleAlert': Alerts,
          'time': SimpleNamespace(monotonic=lambda: self.now), 'cloudlog': Mock(),
          'FirstOrderFilter': Mock(), 'retry': lambda **kw: lambda f: f,
          'sound_list': {1: ('warning.wav', None, 1.), 2: ('warning.wav', None, 1.), 3: ('engage.wav', 1, 1.)}}
    tree = ast.parse((HERE / 'soundd.chime.py').read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Soundd')
    exec(compile(ast.Module(body=[cls], type_ignores=[]), 'soundd.chime.py', 'exec'), ns)
    self.cls = ns['Soundd']
    self.cls.load_sounds = lambda s: setattr(s, 'loaded_sounds', {i: np.full(6000, .8, np.float32) for i in (1, 2, 3)})
    self.s = self.cls()
    class SM(dict):
      pass
    self.sm = SM(selfdriveState=SimpleNamespace(enabled=False), soundPressure=SimpleNamespace(soundPressureWeightedDb=45., soundPressureWeighted=.001))
    self.sm.updated = {'soundPressure': True}
    self.sm.valid = {'soundPressure': True, 'selfdriveState': True}
    self.sm.logMonoTime = {'soundPressure': int(100e9), 'selfdriveState': int(100e9)}
    self.stream = SimpleNamespace(active=True)
    self.out = np.zeros((4096, 1), np.float32)

  def tearDown(self):
    self.tmp.cleanup()

  def callback(self):
    self.s.callback(self.out, 4096, None, None)

  def arm(self):
    self.callback()
    self.s.maybe_audio_ready(self.sm, self.stream)

  def test_pcm(self):
    with wave.open(str(self.asset)) as w:
      self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, 48000, 15840))
    self.assertLess(np.max(np.abs(self.s.audio_ready_sound)), .2)

  def test_active_and_callback_required(self):
    self.s.maybe_audio_ready(self.sm, self.stream)
    self.assertFalse(self.s.audio_ready_pending)
    self.callback()
    self.stream.active = False
    self.s.maybe_audio_ready(self.sm, self.stream)
    self.assertFalse(self.s.audio_ready_pending)
    self.stream.active = True
    self.s.maybe_audio_ready(self.sm, self.stream)
    self.assertTrue(self.s.audio_ready_pending)

  def test_fresh_valid_measured_mic_required(self):
    self.callback()
    for attr, key, value in [('updated', 'soundPressure', False), ('valid', 'soundPressure', False), ('valid', 'selfdriveState', False),
                             ('logMonoTime', 'selfdriveState', int(99e9)),
                             ('logMonoTime', 'soundPressure', int(99e9)), ('logMonoTime', 'soundPressure', int(101e9))]:
      mapping = getattr(self.sm, attr)
      old = mapping[key]
      mapping[key] = value
      self.s.maybe_audio_ready(self.sm, self.stream)
      self.assertFalse(self.s.audio_ready_pending)
      mapping[key] = old
    for field, value in [('soundPressureWeighted', 0), ('soundPressureWeightedDb', float('nan'))]:
      old = getattr(self.sm['soundPressure'], field)
      setattr(self.sm['soundPressure'], field, value)
      self.s.maybe_audio_ready(self.sm, self.stream)
      self.assertFalse(self.s.audio_ready_pending)
      setattr(self.sm['soundPressure'], field, old)
    self.s.maybe_audio_ready(self.sm, self.stream)
    self.assertTrue(self.s.audio_ready_pending)

  def test_one_play_then_silence_no_alert_mutation(self):
    self.arm()
    output = []
    for _ in range(6):
      self.callback()
      output.append(self.out[:, 0].copy())
    output = np.concatenate(output)
    np.testing.assert_array_equal(output[:15840], self.s.audio_ready_sound * .5)
    self.assertFalse(np.any(output[15840:]))
    self.assertEqual(self.s.current_alert, Alerts.none)
    self.assertEqual(self.s.current_sound_frame, 0)
    self.s.maybe_audio_ready(self.sm, self.stream)
    self.assertFalse(self.s.audio_ready_pending)

  def test_each_alert_preempts_without_mixing(self):
    for alert in (1, 2, 3):
      with self.subTest(alert=alert):
        self.s = self.cls()
        self.arm()
        self.callback()
        self.s.update_alert(alert)
        self.callback()
        np.testing.assert_array_equal(self.out[:, 0], np.full(4096, .8, np.float32) * .1)
        self.assertFalse(self.s.audio_ready_pending)
        self.assertTrue(self.s.audio_ready_done)

  def test_prior_alert_suppresses_cue(self):
    self.s.update_alert(3)
    self.s.current_alert = 0
    self.arm()
    self.assertFalse(self.s.audio_ready_pending)

  def test_engaged_timeout_or_late_start_suppresses(self):
    for case in ('enabled', 'timeout', 'late'):
      with self.subTest(case=case):
        self.s = self.cls()
        self.sm['selfdriveState'].enabled = case == 'enabled'
        self.s.selfdrive_timeout_alert = case == 'timeout'
        self.now += 21 if case == 'late' else 0
        self.arm()
        self.assertFalse(self.s.audio_ready_pending)
        self.assertTrue(self.s.audio_ready_done)

  def test_missing_asset_is_nonfatal(self):
    self.asset.unlink()
    self.s = self.cls()
    self.assertTrue(self.s.audio_ready_done)
    self.s.update_alert(2)
    self.callback()
    self.assertTrue(np.all(self.out > 0))

  def test_bad_asset_is_nonfatal(self):
    self.asset.write_bytes(b'not a WAV')
    self.assertTrue(self.cls().audio_ready_done)

if __name__ == '__main__':
  unittest.main(verbosity=2)
