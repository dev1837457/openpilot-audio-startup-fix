"""Run actual gate and manager-start fragment with OS operations mocked."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent
SOURCE = (ROOT / 'launch_chffrplus.gated.sh').read_text()
HELPER = SOURCE[SOURCE.index('function wait_for_sound {'):SOURCE.index('function launch {')]
FRAGMENT = SOURCE[SOURCE.index('  # Do not start manager'):SOURCE.index('  # if broken, keep on screen error')]


class LauncherGateTests(unittest.TestCase):
  def run_case(self, ready_on=1, query_status=0, agnos=True):
    with tempfile.TemporaryDirectory() as directory:
      root = pathlib.Path(directory)
      manager_dir = root / 'openpilot/system/manager'
      manager_dir.mkdir(parents=True)
      (root / 'prebuilt').touch()
      manager = manager_dir / 'manager.py'
      manager.write_text('#!/usr/bin/env bash\necho started > "$DIR/manager-started"\n')
      manager.chmod(0o755)
      # Keep the gate and launch fragment unmodified except the log destination.
      script = '''
export DIR="$PWD"
checks=0
timeout() {
  if [[ "$1" != --kill-after=1s || "$2" != 1s ]]; then exit 90; fi
  shift 2
  "$@"
}
systemctl() {
  if [[ "$*" != 'is-active --quiet sound.target' ]]; then exit 91; fi
  ((checks+=1))
  echo "$checks" > "$DIR/checks"
  if (( QUERY_STATUS != 0 )); then return "$QUERY_STATUS"; fi
  (( checks >= READY_ON ))
}
sleep() { [[ "$*" == 1 ]] || exit 92; }
[() {
  if [[ "$1" == -f && "$2" == /AGNOS ]]; then return "$AGNOS_TEST_STATUS"; fi
  builtin [ "$@"
}
'''
      script += HELPER + '\nfunction launch {\n' + FRAGMENT.replace('/tmp/launch_log', '"$DIR/launch_log"') + '\n}\nlaunch\n'
      env = {'PATH': '/usr/bin:/bin', 'READY_ON': str(ready_on), 'QUERY_STATUS': str(query_status),
             'AGNOS_TEST_STATUS': '0' if agnos else '1'}
      result = subprocess.run(['bash', '-c', script], cwd=root, env=env, capture_output=True, text=True, timeout=5)
      count = int((root / 'checks').read_text()) if (root / 'checks').exists() else 0
      return result, (root / 'manager-started').exists(), count

  def test_immediately_ready(self):
    result, started, count = self.run_case()
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue(started)
    self.assertEqual(count, 1)

  def test_eventual_readiness(self):
    result, started, count = self.run_case(ready_on=7)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue(started)
    self.assertEqual(count, 7)

  def test_permanently_inactive_fails_closed(self):
    result, started, count = self.run_case(ready_on=61)
    self.assertEqual(result.returncode, 1)
    self.assertFalse(started)
    self.assertEqual(count, 60)
    self.assertIn('manager NOT started', result.stderr)

  def test_query_timeout_fails_closed(self):
    result, started, count = self.run_case(query_status=124)
    self.assertEqual(result.returncode, 1)
    self.assertFalse(started)
    self.assertEqual(count, 60)

  def test_non_agnos_unchanged(self):
    result, started, count = self.run_case(agnos=False)
    self.assertEqual(result.returncode, 0, result.stderr)
    self.assertTrue(started)
    self.assertEqual(count, 0)

  def test_overlay_and_hardware_initialization_remain_before_gate(self):
    launch = SOURCE[SOURCE.index('function launch {'):]
    self.assertLess(launch.index('exec "${LAUNCHER_LOCATION}"'), launch.index('if ! wait_for_sound'))
    self.assertLess(launch.index('\n    agnos_init\n'), launch.index('if ! wait_for_sound'))
    self.assertLess(launch.index('if ! wait_for_sound'), launch.index('./manager.py'))


if __name__ == '__main__':
  unittest.main()
