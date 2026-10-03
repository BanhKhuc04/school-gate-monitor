import {useEffect, useRef, useState} from 'react';
import client from '../api/client';

const REASONS = {track_missing:'Chưa có track ổn định', vehicle_not_associated:'Chưa ghép được xe; biển chỉ là ứng viên',
  vehicle_association_ambiguous:'Có nhiều xe gần nhau — chưa ghép chắc chắn',
  helmet_association_ambiguous:'Chưa ghép chắc mũ với người', plate_association_ambiguous:'Có nhiều ứng viên biển — cần kiểm tra'};
const COLORS = {confirmed:'bg-emerald-100 text-emerald-900', checking:'bg-slate-100 text-slate-700',
  review:'bg-amber-100 text-amber-900', error:'bg-red-100 text-red-900'};
const HEAD = {helmet:'Có mũ', no_helmet:'Quan sát không mũ', unknown:'Chưa thấy rõ đầu/mũ'};
const PLATE = {missing:'Chưa thấy biển', reading:'Đang đọc OCR', error:'OCR lỗi',
  selecting:'Đang chọn ảnh biển tốt nhất — chờ gần vạch',
  candidate:'Biển đọc thử', confirmed:'Biển đã đối chiếu', partial:'Đọc được một phần — chưa đủ toàn biển',
  unreadable:'Chưa đọc được ký tự', review:'Chưa đủ điều kiện OCR'};

function Crop({image, label, className=''}) {
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[image?.url]);
  return <figure className={`rounded-lg bg-slate-950/10 overflow-hidden ${className}`}>
    <figcaption className="px-2 py-1 text-[11px] font-semibold">{label}{image && <span className="font-normal opacity-60"> · frame {image.frame_seq}{image.timestamp && ` · ${new Date(image.timestamp).toLocaleTimeString('vi-VN',{hour12:false})}`}</span>}</figcaption>
    {image && !failed ? <img src={image.url} alt={`Ảnh ${label.toLowerCase()}`} onError={()=>setFailed(true)} className="w-full h-[calc(100%-24px)] object-contain"/> :
      <div className="flex items-center justify-center h-[calc(100%-24px)] p-2 text-xs text-center opacity-60">{failed?'Ảnh đã hết hạn':'Chưa có ảnh'}</div>}
  </figure>;
}

function Samples({label, result}) {
  return <div className="flex items-center justify-between gap-2 text-xs">
    <span>{label}</span><span className={`rounded px-2 py-1 ${COLORS[result.state] || COLORS.review}`}>
      {result.samples}/{result.required_samples} mẫu · {result.state==='confirmed'?'Đã đối chiếu':result.state==='review'?'Cần kiểm tra':result.state==='error'?'Lỗi model':'Đang kiểm tra'}
    </span>
  </div>;
}

export default function RecognitionLogPanel({gate}) {
  const [info,setInfo]=useState(null), [error,setError]=useState(''), [track,setTrack]=useState('');
  const [paused,setPaused]=useState(false), [hidden,setHidden]=useState({}), [retry,setRetry]=useState(0);
  const pauseRef=useRef(false);
  useEffect(()=>{pauseRef.current=paused;},[paused]);
  useEffect(()=>{
    let active=true, timer, request, run=null, epoch=null;
    const poll=async()=>{
      request=new AbortController();
      try {
        const {data}=await client.get('/guard/recognition_cards',{params:{gate},signal:request.signal});
        if(!active)return;
        const reset=run!==data.run_id || epoch!==data.source_epoch;
        run=data.run_id;epoch=data.source_epoch;
        if(reset)setHidden({});
        if(!pauseRef.current || reset)setInfo(data);
        setError('');
      } catch(err) {
        if(active && !request.signal.aborted)setError(err.response?.data?.detail || 'Không tải được thẻ nhận diện.');
      } finally {if(active)timer=setTimeout(poll,1000);}
    };
    poll();return()=>{active=false;clearTimeout(timer);request?.abort();};
  },[gate,retry]);
  const cards=info?.cards || [];
  const visible=cards.filter(c=>(!track || String(c.track_id ?? '')===track || String(c.vehicle_track_id ?? '')===track)
    && c.frame_seq>(hidden[c.card_id] ?? -1));
  return <section aria-label="Nhận diện bằng hình ảnh" className="flex flex-col gap-3 min-h-0">
    <p className="text-xs text-white/80">Đối chiếu nhiều frame của cùng track. Track ổn định chưa xác nhận danh tính học sinh; nhận diện này không phát loa.</p>
    <details className="text-xs rounded-lg bg-white/10 p-3">
      <summary className="cursor-pointer font-semibold">Model đang dùng · {info?.models?.tracker?.engine || 'Đang tải'}</summary>
      <div className="space-y-1 mt-2">{['person','helmet','plate'].map(key=><p key={key} className="break-all">
        {{person:'Người/xe',helmet:'Mũ',plate:'Biển'}[key]}: {info?.models?.[key]?.family || 'Chưa có thông tin'} · {info?.models?.[key]?.weights || '—'} · {info?.models?.[key]?.device || '—'}
      </p>)}<p>OCR: {info?.models?.ocr?.engine || '—'}</p></div>
    </details>
    {info?.models?.helmet?.status==='error' && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">Nhận diện mũ chưa khả dụng: model chưa hợp lệ.</div>}
    {info?.status==='not_started' && <p role="status">Pipeline chưa khởi động.</p>}
    {info?.status==='stopped' && <p role="status" className="text-amber-200">Pipeline đã dừng; ảnh dưới là quan sát cuối.</p>}
    {info?.gate_line_configured===false && <p role="status" className="rounded bg-amber-100 text-amber-900 p-3 text-xs">Chưa cấu hình vạch cổng: vẫn hiển thị nhận diện; OCR của xe đã ghép và cảnh báo qua cổng đang chờ vạch. <a href="/admin/roi" className="underline">Cấu hình vùng và vạch cổng</a></p>}
    {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error} <button className="underline" onClick={()=>setRetry(v=>v+1)}>Thử lại</button></div>}
    <div className="flex flex-wrap gap-2 text-xs">
      <input aria-label="Lọc track" placeholder="ID người hoặc xe" value={track} onChange={e=>setTrack(e.target.value)} className="rounded bg-primary-container text-on-primary-container px-2 py-2 w-32"/>
      <button onClick={()=>setPaused(v=>!v)} aria-pressed={paused} className="rounded border border-white/30 px-2 py-2">{paused?'Tiếp tục cập nhật':'Tạm dừng cập nhật'}</button>
      <button onClick={()=>setHidden(Object.fromEntries(cards.map(c=>[c.card_id,c.frame_seq])))} className="rounded border border-white/30 px-2 py-2">Ẩn thẻ hiện tại</button>
    </div>
    {paused && <p className="text-xs text-amber-200">Đang tạm dừng cập nhật thẻ; camera vẫn chạy.</p>}
    <div className="space-y-3 overflow-y-auto max-h-[70vh] pr-1" data-testid="recognition-cards">
      {!visible.length && <p role="status" className="text-sm bg-primary-container text-on-primary-container rounded p-3">{!info && !error?'Đang tải nhận diện…':track?'Không có thẻ phù hợp bộ lọc.':'Chưa có đối tượng mới trong vùng nhận diện.'}</p>}
      {visible.map(card=><article key={card.card_id} data-testid="recognition-card" className="rounded-xl bg-primary-container text-on-primary-container p-3 space-y-3 border border-white/15">
        <header className="flex justify-between gap-2"><div><p className="font-semibold">{card.kind==='plate' ? 'Biển số chưa ghép xe' : `Người #${card.track_id ?? 'chưa có ID'}`}</p><p className="text-[11px] opacity-70">{card.camera_id}{card.vehicle_track_id!=null && ` · Xe #${card.vehicle_track_id}`}</p></div><time className="text-xs">{new Date(card.last_seen).toLocaleTimeString('vi-VN',{hour12:false})}</time></header>
        {card.kind==='plate' ? <Crop image={card.images?.plate} label="Biển số" className="h-[150px]"/> : <>
        <div className="grid grid-cols-[.8fr_1.2fr] gap-2">
          <Crop image={card.images?.person} label="Người" className="row-span-2 h-[218px]"/>
          <Crop image={card.images?.head} label="Đầu / mũ" className="h-[105px]"/>
          <Crop image={card.images?.plate} label="Biển số" className="h-[105px]"/>
        </div>
        <Samples label="Theo dõi người" result={card.person}/>
        <Samples label={HEAD[card.helmet.value] || HEAD.unknown} result={card.helmet}/>
        </>}
        <div className={`rounded-lg px-3 py-2 text-xs ${card.plate.state==='confirmed'?COLORS.confirmed:card.plate.state==='error'?COLORS.error:COLORS.review}`}>
          <p className="font-semibold">{PLATE[card.plate.state] || 'Biển cần kiểm tra'}</p>
          {card.plate.text && <p className="font-mono text-lg mt-1 tracking-wide">{card.plate.text}</p>}
          <p>{card.plate_debug?.max_attempts ? `${card.plate_debug.attempts}/1 lượt OCR · chọn một crop tốt nhất` : card.vehicle_track_id==null ? 'Chưa ghép xe — chưa thực hiện OCR' : '0/1 lượt OCR · chờ crop biển phù hợp'}</p>
          {card.plate_debug?.best_frame_id != null && <div className="mt-2 space-y-1">
            <p>Ảnh chọn: frame {card.plate_debug.best_frame_id} · {card.plate_debug.size?.join('×')} px gốc</p>
            <p>Chất lượng crop: {card.plate_debug.quality} · độ nét: {card.plate_debug.blur}</p>
            <p>Confidence box: {card.plate_debug.detector_confidence} · tương phản: {card.plate_debug.contrast}</p>
            <p>Trạng thái: {card.plate_debug.status}{card.plate_debug.technical_retries>0 && ` · thử lại do lỗi kỹ thuật: ${card.plate_debug.technical_retries}`}</p>
            <a href={`/guard/plate_best/${card.ocr_track_id ?? card.vehicle_track_id}?gate=${encodeURIComponent(gate)}&epoch=${card.source_epoch}`} className="underline" download>Tải ảnh biển đã chọn</a>
            <details><summary className="cursor-pointer">Chi tiết OCR</summary>
              <p>Dòng trên: {card.plate_debug.raw_top || '—'}</p><p>Dòng dưới: {card.plate_debug.raw_bottom || '—'}</p>
              <p>Toàn biển: {card.plate_debug.normalized || 'Chưa đọc đủ'}</p>
            </details>
          </div>}
          {card.riding?.state && <p className="mt-2">Hành vi: {card.riding.state==='RIDING'?'Đang đi xe':card.riding.state==='WALKING_WITH_BIKE'?'Dắt xe':'Chưa xác định'} · chân: {card.riding.leg_status==='AVAILABLE'?'quan sát được':'không đủ quan sát'}</p>}
          {card.riding?.state && <details><summary className="cursor-pointer">Chi tiết tư thế</summary>
            <p>Hip: {card.riding.hip_score ?? 'Không quan sát được'} · torso: {card.riding.torso_score ?? 'Không quan sát được'}</p>
            <p>Overlap: {card.riding.overlap ?? '—'} · temporal: {card.riding.temporal ?? '—'} · motion: {card.riding.motion ?? '—'}</p>
            <p>Score: {card.riding.score ?? '—'} · chân: {card.riding.leg_status}</p>
          </details>}
          {card.plate.association==='unverified' && <p className="mt-1 font-semibold">Chưa ghép xe — không gán học sinh</p>}
        </div>
        {card.reasons?.length>0 && <p className="text-[11px] opacity-80">{card.reasons.map(r=>REASONS[r] || r).join(' · ')}</p>}
        {card.images_state==='error' && <p role="alert" className="text-xs text-red-800">Không tạo được ảnh crop; kết quả nhận diện cần kiểm tra.</p>}
      </article>)}
    </div>
  </section>;
}
