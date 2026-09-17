"""Listen to a configured audio input and print levels; sends no MIDI."""

import argparse
import time

import numpy as np
from logicprogym.audio import AudioInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    parser.add_argument('--source', choices=['device', 'native'], default='device')
    parser.add_argument('--bundle-id', default='auto',
                        help='Application identifier; default auto-detects either Logic edition')
    parser.add_argument('--build-dir', help='Optional directory for the native helper build')
    parser.add_argument('--device', help='Audio input device name')
    parser.add_argument('--sample-rate', type=int, default=None)
    parser.add_argument('--channels', type=int, default=2)
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    if args.list:
        if args.source == 'native':
            import subprocess
            from logicprogym.native_audio import build_helper
            subprocess.run([str(build_helper(args.build_dir)), '--list'], check=True, timeout=10)
            return
        import sounddevice
        print(sounddevice.query_devices())
        return
    if (args.source == 'device' and not args.device) or not 0 < args.seconds < float('inf'):
        parser.error('Device capture needs --device; --seconds must be finite and positive')
    if args.source == 'native':
        from logicprogym.native_audio import NativeAudioInput
        audio = NativeAudioInput(args.bundle_id, sample_rate=args.sample_rate,
                                 channels=args.channels, build_dir=args.build_dir)
    else:
        audio = AudioInput(args.device, sample_rate=args.sample_rate or 48000, channels=args.channels)
    try:
        audio.start()
        if args.source == 'native':
            print(f'Capturing {audio.resolved_bundle_id}', flush=True)
        print('Play audio in Logic. Ctrl-C stops capture.', flush=True)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            data, valid, info = audio.read()
            samples = data[valid.astype(bool)]
            rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0
            peak = float(np.max(np.abs(samples))) if len(samples) else 0
            print(f'audio frames={int(valid.sum())} RMS={rms:.5f} peak={peak:.5f} '
                  f"age={info['age_seconds']} status_count={info['callback_status_count']}", flush=True)
            time.sleep(.25)
    except KeyboardInterrupt:
        print('\nStopping audio capture.', flush=True)
    except (RuntimeError, ValueError, OSError) as error:
        parser.exit(1, f'Audio capture failed: {error}\n')
    finally:
        audio.close()
        print('Audio input closed.', flush=True)


if __name__ == '__main__':
    main()
