"""Compare logging on/off on identical local-video frames in a disposable DB.

This checks instrumentation overhead, not recognition accuracy or RTSP latency.
No running camera source, operating DB or media is modified.
"""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', required=True)
    parser.add_argument('--frames', type=int, default=40)
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if args.frames < 10 or args.repeats < 2:
        parser.error('Use at least 10 frames and two repetitions.')
    os.environ['CONTINUOUS_RECORDING_ENABLED'] = '0'
    os.environ['HELMET_MODEL_PATH'] = str(Path('models/backups/helmet_best_20260930_090903.pt').resolve())
    import cv2
    import torch
    import app.config as cfg
    cfg.DEVICE = 'cpu'  # keep the live viewer GPU workload separate
    torch.set_num_threads(2)
    cap = cv2.VideoCapture(args.video)
    frames = []
    try:
        for index in range(args.frames * 5):
            ok, frame = cap.read()
            if not ok:
                break
            if index % 5 == 0:
                frames.append(cv2.resize(frame, (cfg.VIDEO_WIDTH, cfg.VIDEO_HEIGHT)))
    finally:
        cap.release()
    if len(frames) < 10:
        raise RuntimeError('Video does not contain enough frames.')
    results = []
    with tempfile.TemporaryDirectory(prefix='recognition_bench_') as work:
        cfg.DB_PATH = str(Path(work) / 'app.db')
        cfg.SNAPSHOTS_DIR = str(Path(work) / 'media')
        import app.db as db
        db.init_db()
        import app.cv.pipeline as module
        module.FRAME_SKIP = 1
        # Reuse warmed real models. Reload/fusion variance must not be attributed
        # to a 500-row log buffer; reset tracking before each identical replay.
        detector_factory = module.HelmetPlateDetector
        model_cache = {}
        def cached_detector(path, **kwargs):
            if path not in model_cache:
                model_cache[path] = detector_factory(path, **kwargs)
            return model_cache[path]
        module.HelmetPlateDetector = cached_detector
        for run in range(1 + args.repeats * 2):
            enabled = run > 0 and run % 2 == 0
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline = module.VideoPipeline('main', {'source': 'isolated-video', 'name': 'Benchmark'})
                pipeline._recognition_logging_enabled = enabled
                diagnostic_time = [0.0]
                original_diagnostic = pipeline._diagnostic
                def timed_diagnostic(*args, **kwargs):
                    start = time.perf_counter()
                    try:
                        return original_diagnostic(*args, **kwargs)
                    finally:
                        diagnostic_time[0] += time.perf_counter() - start
                pipeline._diagnostic = timed_diagnostic
                class Source:
                    index = 0
                    def read_frame(self):
                        frame = frames[self.index].copy()
                        self.index += 1
                        if self.index == len(frames):
                            pipeline._running = False
                        return frame
                    def release(self):
                        pass
                pipeline._open_webcam = lambda config: Source()
                pipeline._ocr_init_reader()  # exclude one-time OCR startup from timings
                for tracker in getattr(getattr(pipeline._person_detector.model, 'predictor', None), 'trackers', []):
                    tracker.reset()
                for detector in [pipeline._person_detector, pipeline._helmet_detector, pipeline._plate_detector]:
                    detector.detect(cv2.resize(frames[0], (cfg.DETECT_WIDTH, cfg.DETECT_HEIGHT)))
                pipeline._running = True
                start = time.perf_counter()
                pipeline._run_loop()
                elapsed = time.perf_counter() - start
                for pool in [pipeline._detect_pool, pipeline._ocr_pool, pipeline._io_pool, pipeline._clip_pool]:
                    pool.shutdown(wait=True)
                rows = pipeline._recognition_log.snapshot(limit=100)['items']
                result = {'logging': enabled, 'seconds': elapsed, 'fps': len(frames) / elapsed,
                          'frames': len(frames), 'ocr': pipeline._ocr_health,
                          'diagnostic_ms': diagnostic_time[0] * 1000,
                          'diagnostic_share_percent': diagnostic_time[0] / elapsed * 100,
                          'buffer_rows': pipeline._recognition_log.size,
                          'last_reasons': sorted({r['reason_code'] for r in rows})}
            if run:
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)
        off = statistics.median(r['seconds'] for r in results if not r['logging'])
        on = statistics.median(r['seconds'] for r in results if r['logging'])
        report = {'profile': 'one local video, CPU, warmed/reused real detectors + pose + async OCR + JPEG; tracker reset each run; no viewers',
                  'video': str(Path(args.video).resolve()), 'runs': results,
                  'video_sha256': hashlib.file_digest(open(args.video, 'rb'), 'sha256').hexdigest(),
                  'helmet_model_sha256': hashlib.file_digest(open(os.environ['HELMET_MODEL_PATH'], 'rb'), 'sha256').hexdigest(),
                  'median_off_sec': off, 'median_on_sec': on,
                  'median_overhead_percent': (on / off - 1) * 100,
                  'limitations': 'Does not certify two-camera FPS, LAN latency, UI overhead or recognition precision.'}
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({k: v for k, v in report.items() if k != 'runs'}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
