"""Regression check using faster-whisper's actual decoder, including MP4/AAC."""
import io
import wave

import av
import numpy as np
from faster_whisper.audio import decode_audio


def check_decoding():
    pcm = (np.sin(np.arange(32000) * (440 * 2 * np.pi / 16000)) * 12000).astype(np.int16)
    wav = io.BytesIO()
    with wave.open(wav, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(pcm.tobytes())
    wav.seek(0)
    decoded = decode_audio(wav)
    assert len(decoded) == 32000 and np.max(np.abs(decoded)) > .1

    mp4 = io.BytesIO()
    with av.open(mp4, 'w', format='mp4') as output:
        stream = output.add_stream('aac', rate=16000)
        stream.layout = 'mono'
        frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format='s16', layout='mono')
        frame.sample_rate = 16000
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    mp4.seek(0)
    decoded = decode_audio(mp4)
    assert 31000 <= len(decoded) <= 34000 and np.max(np.abs(decoded)) > .1


if __name__ == '__main__':
    check_decoding()
    print('PASS: faster-whisper decodes WAV and MP4/AAC using PyAV ' + av.__version__)
