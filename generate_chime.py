"""Original 330ms descending three-note cue; no engagement asset is used."""
from pathlib import Path
import math
import struct
import wave

rate = 48000
samples = []
for frequency in (1046.502, 783.991, 622.254):
  for i in range(int(rate * 0.11)):
    t = i / rate
    # Smooth start/end and a quiet bell-like second partial.
    envelope = math.sin(math.pi * i / (int(rate * 0.11) - 1)) ** 2
    samples.append(round(32767 * 0.16 * envelope * (0.85 * math.sin(2 * math.pi * frequency * t) +
                                                  0.15 * math.sin(4 * math.pi * frequency * t))))
with wave.open(str(Path(__file__).with_name('audio_ready.wav')), 'wb') as wav:
  wav.setparams((1, 2, rate, len(samples), 'NONE', 'not compressed'))
  wav.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
