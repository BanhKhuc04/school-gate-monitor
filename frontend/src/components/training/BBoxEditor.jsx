import {useCallback, useEffect, useRef, useState} from 'react';

/**
 * BBoxEditor — Training component (Slice A) cho phép chỉnh bbox chuẩn hoá
 * trên ảnh crop/ảnh ngữ cảnh. KHÔNG dùng để auto-fill học sinh.
 *
 * Input:
 *   - src (string, bắt buộc): URL ảnh (crop hoặc full frame).
 *   - initialBBox (array|null): [x1, y1, x2, y2] đã chuẩn hoá 0..1.
 *     null/undefined = tạo mới (canvas mở với bbox mặc định bao trùng ~80% vùng giữa).
 *   - canEdit (bool): chỉ enable khi role hợp lệ (admin/teacher).
 *   - imageKind ('crop' | 'full'): gợi ý marker; editor vẫn xử lý giống nhau.
 *   - onChange (fn): callback mỗi khi bbox thay đổi hợp lệ.
 *   - onSubmit (fn): callback khi user bấm "Lưu". Args: bbox, reason.
 *   - busy (bool): disable nút khi đang submit.
 *
 * Behavior:
 *   - Drag đỉnh (handle) để resize; drag vùng trong để di chuyển.
 *   - Tọa độ chuẩn hoá 0..1, snap về 0.001 khi release.
 *   - Phím Delete/Backspace xoá bbox hiện tại (set null) khi có bbox.
 *   - Phím Enter gọi onSubmit với reason mặc định 'manual_edit'.
 *   - Escape huỷ chỉnh về initialBBox.
 *   - Validate luôn: [x1<x2, y1<y2, diện tích >= 1% ảnh].
 *
 * KHÔNG auto-điền. KHÔNG auto-assign student. KHÔNG thay model runtime.
 */
const MIN_AREA_PCT = 0.005; // 0.5% image area

function clamp01(v) {
  return Math.max(0, Math.min(1, v));
}

function snap(v) {
  return Math.round(v * 1000) / 1000;
}

function normalizeBBox(b) {
  if (!b || !Array.isArray(b) || b.length !== 4) return null;
  const [a, b1, c, d] = b.map(Number);
  if ([a, b1, c, d].some(v => !Number.isFinite(v))) return null;
  const x1 = Math.min(a, c);
  const y1 = Math.min(b1, d);
  const x2 = Math.max(a, c);
  const y2 = Math.max(b1, d);
  return [snap(x1), snap(y1), snap(x2), snap(y2)];
}

function defaultBBox() {
  return [0.1, 0.1, 0.9, 0.9];
}

function BBoxValid(b) {
  if (!b) return false;
  const [x1, y1, x2, y2] = b;
  if (x2 - x1 < 0.01) return false;
  if (y2 - y1 < 0.01) return false;
  if ((x2 - x1) * (y2 - y1) < MIN_AREA_PCT) return false;
  return true;
}

const HANDLES = [
  {name: 'nw', cursor: 'nwse-resize', ix: 0, iy: 1},
  {name: 'n', cursor: 'ns-resize', ix: 0, iy: 0.5, line: true},
  {name: 'ne', cursor: 'nesw-resize', ix: 1, iy: 1},
  {name: 'e', cursor: 'ew-resize', ix: 1, iy: 0.5, line: true},
  {name: 'se', cursor: 'nwse-resize', ix: 1, iy: 0},
  {name: 's', cursor: 'ns-resize', ix: 0.5, iy: 0, line: true},
  {name: 'sw', cursor: 'nesw-resize', ix: 0, iy: 0},
  {name: 'w', cursor: 'ew-resize', ix: 0, iy: 0.5, line: true},
];

export default function BBoxEditor({
  src,
  initialBBox = null,
  canEdit = false,
  imageKind = 'crop',
  onChange = () => {},
  onSubmit = null,
  busy = false,
  hints = null,
}) {
  const containerRef = useRef(null);
  const imgRef = useRef(null);
  const [bbox, setBBox] = useState(() => normalizeBBox(initialBBox) || defaultBBox());
  const [drag, setDrag] = useState(null); // {mode:'move'|'resize', handle, startMouse, startBBox}
  const [imageSize, setImageSize] = useState({w: 0, h: 0});
  const [imgReady, setImgReady] = useState(false);
  const [imageError, setImageError] = useState(false);

  useEffect(() => { setImgReady(false); setImageError(false); }, [src]);

  useEffect(() => {
    setBBox(normalizeBBox(initialBBox) || defaultBBox());
  }, [initialBBox, src]);

  const onImgLoad = useCallback(e => {
    const el = e.target;
    setImageSize({w: el.naturalWidth, h: el.naturalHeight});
    setImgReady(true);
  }, []);

  const applyBBox = useCallback(
    next => {
      const norm = normalizeBBox(next);
      if (!norm) return;
      setBBox(norm);
      onChange(norm);
    },
    [onChange]
  );

  const getRelXY = useCallback(evt => {
    const el = containerRef.current;
    if (!el) return {x: 0, y: 0};
    const r = el.getBoundingClientRect();
    return {
      x: clamp01((evt.clientX - r.left) / r.width),
      y: clamp01((evt.clientY - r.top) / r.height),
    };
  }, []);

  const onPointerDown = useCallback(
    (mode, handle = null) => evt => {
      if (!canEdit || !imgReady || busy) return;
      evt.preventDefault();
      evt.stopPropagation();
      const rel = getRelXY(evt);
      setDrag({mode, handle, startMouse: rel, startBBox: bbox});
    },
    [canEdit, imgReady, busy, bbox, getRelXY]
  );

  useEffect(() => {
    if (!drag) return;
    const onMove = evt => {
      const rel = getRelXY(evt);
      const dx = rel.x - drag.startMouse.x;
      const dy = rel.y - drag.startMouse.y;
      const sb = drag.startBBox;
      let next = sb;
      if (drag.mode === 'move') {
        const w = sb[2] - sb[0];
        const h = sb[3] - sb[1];
        let nx1 = clamp01(sb[0] + dx);
        let ny1 = clamp01(sb[1] + dy);
        nx1 = clamp01(nx1);
        ny1 = clamp01(ny1);
        next = [nx1, ny1, clamp01(nx1 + w), clamp01(ny1 + h)];
      } else {
        const h = drag.handle;
        const ix = h.ix; // 0 left, 1 right
        const iy = h.iy; // 0 bottom, 1 top
        let {x1, y1, x2, y2} = {x1: sb[0], y1: sb[1], x2: sb[2], y2: sb[3]};
        if (ix === 0) x1 = clamp01(sb[0] + dx);
        if (ix === 1) x2 = clamp01(sb[2] + dx);
        if (iy === 0) y2 = clamp01(sb[3] + dy);
        if (iy === 1) y1 = clamp01(sb[1] + dy);
        next = [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)];
      }
      applyBBox(next);
    };
    const onUp = () => setDrag(null);
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
    };
  }, [drag, getRelXY, applyBBox]);

  const onKeyDown = useCallback(
    evt => {
      if (!canEdit || !imgReady || busy) return;
      if (evt.key === 'Escape') {
        setBBox(normalizeBBox(initialBBox) || defaultBBox());
      } else if (evt.key === 'Delete' || evt.key === 'Backspace') {
        evt.preventDefault();
        setBBox(defaultBBox());
      } else if (evt.key === 'Enter') {
        evt.preventDefault();
        if (onSubmit && BBoxValid(bbox)) onSubmit(bbox, 'manual_edit');
      } else if (evt.key === 'ArrowUp' || evt.key === 'ArrowDown' || evt.key === 'ArrowLeft' || evt.key === 'ArrowRight') {
        evt.preventDefault();
        const step = evt.shiftKey ? 0.05 : 0.005;
        let [x1, y1, x2, y2] = bbox;
        if (evt.key === 'ArrowUp') {
          y1 = clamp01(y1 - step);
          y2 = clamp01(y2 - step);
        } else if (evt.key === 'ArrowDown') {
          y1 = clamp01(y1 + step);
          y2 = clamp01(y2 + step);
        } else if (evt.key === 'ArrowLeft') {
          x1 = clamp01(x1 - step);
          x2 = clamp01(x2 - step);
        } else if (evt.key === 'ArrowRight') {
          x1 = clamp01(x1 + step);
          x2 = clamp01(x2 + step);
        }
        applyBBox([x1, y1, x2, y2]);
      }
    },
    [canEdit, imgReady, busy, bbox, initialBBox, onSubmit, applyBBox]
  );

  const handleSubmit = () => {
    if (!onSubmit || !BBoxValid(bbox) || !canEdit || !imgReady || busy) return;
    onSubmit(bbox, 'manual_edit');
  };

  const valid = BBoxValid(bbox);
  const [x1, y1, x2, y2] = bbox;

  return (
    <div className="rounded border border-slate-300 bg-white p-3">
      <div className="mb-2 flex items-center justify-between text-sm text-slate-700">
        <div>
          <strong>Box chuẩn hoá</strong> ({imageKind}){' '}
          {imageSize.w > 0 && (
            <span className="text-xs text-slate-500">
              · ảnh gốc {imageSize.w}×{imageSize.h}px
            </span>
          )}
        </div>
        {hints && <div className="text-xs text-slate-500">{hints}</div>}
      </div>
      <div
        ref={containerRef}
        className="relative w-full overflow-hidden rounded border border-slate-200 bg-slate-50"
        style={{aspectRatio: imageSize.w > 1 && imageSize.h > 1 ? `${imageSize.w} / ${imageSize.h}` : '4 / 3'}}
        tabIndex={0}
        onKeyDown={onKeyDown}
        role="img"
        aria-label="BBox editor canvas"
      >
        {src ? (
          <img
            ref={imgRef}
            src={src}
            alt="bbox target"
            onLoad={onImgLoad}
            onError={() => { setImgReady(false); setImageError(true); }}
            className="absolute inset-0 h-full w-full select-none object-contain"
            draggable={false}
          />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center text-sm text-slate-400">
            Chưa có ảnh
          </div>
        )}
        {imgReady && (
          <>
            <div
              data-testid="bbox-overlay"
              className="absolute border-2 border-emerald-500 bg-emerald-500/10"
              style={{
                left: `${x1 * 100}%`,
                top: `${y1 * 100}%`,
                width: `${(x2 - x1) * 100}%`,
                height: `${(y2 - y1) * 100}%`,
                cursor: canEdit ? 'move' : 'default',
                pointerEvents: canEdit ? 'auto' : 'none',
              }}
              onPointerDown={onPointerDown('move')}
              role="region"
              aria-label="BBox drag area"
            />
            {HANDLES.map(h => {
              if (h.line) return null;
              const left = `${(x1 + (x2 - x1) * h.ix) * 100}%`;
              const top = `${(y1 + (y2 - y1) * h.iy) * 100}%`;
              return (
                <button
                  type="button"
                  key={h.name}
                  data-testid={`bbox-handle-${h.name}`}
                  className="absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-sm border border-white bg-emerald-600 shadow"
                  style={{left, top, cursor: canEdit ? h.cursor : 'default'}}
                  onPointerDown={onPointerDown('resize', h)}
                  onKeyDown={event => {
                    if (!canEdit || busy || !event.key.startsWith('Arrow')) return;
                    event.preventDefault(); event.stopPropagation();
                    const next = [...bbox];
                    const step = event.shiftKey ? .05 : .005;
                    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') next[h.ix === 0 ? 0 : 2] = clamp01(next[h.ix === 0 ? 0 : 2] + (event.key === 'ArrowLeft' ? -step : step));
                    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') next[h.iy === 1 ? 1 : 3] = clamp01(next[h.iy === 1 ? 1 : 3] + (event.key === 'ArrowUp' ? -step : step));
                    applyBBox(next);
                  }}
                  disabled={!canEdit || busy}
                  aria-label={`Resize handle ${h.name}`}
                />
              );
            })}
          </>
        )}
      </div>
      {imageError && <p role="alert" className="mt-2 text-sm text-rose-700">Không tải được ảnh nguồn. Bổ sung ảnh trước khi sửa bbox.</p>}
      <div className="mt-2 flex items-center justify-between gap-2 text-xs text-slate-600">
        <div>
          <span data-testid="bbox-coords">
            [{x1.toFixed(3)}, {y1.toFixed(3)}, {x2.toFixed(3)}, {y2.toFixed(3)}]
          </span>{' '}
          {!valid && <span className="text-rose-600">· bbox không hợp lệ</span>}
        </div>
        {onSubmit && (
          <button
            type="button"
            disabled={!valid || !canEdit || !imgReady || busy}
            onClick={handleSubmit}
            className="rounded bg-emerald-600 px-3 py-1 text-white shadow disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? 'Đang lưu…' : 'Lưu bbox'}
          </button>
        )}
      </div>
    </div>
  );
}

export {BBoxValid, normalizeBBox, defaultBBox};
