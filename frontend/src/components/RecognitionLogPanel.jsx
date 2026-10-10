import {useEffect, useRef, useState} from 'react';
import client from '../api/client';
import {useLang, localeOf} from '../i18n/LanguageContext';

const REASONS = (t) => ({track_missing:t('Chưa có track ổn định','No stable track yet'), vehicle_not_associated:t('Chưa ghép được xe; biển chỉ là ứng viên','No bike matched yet; plate is only a candidate'),
  vehicle_association_ambiguous:t('Có nhiều xe gần nhau — chưa ghép chắc chắn','Several bikes close together — match not certain'),
  helmet_association_ambiguous:t('Chưa ghép chắc mũ với người','Helmet not reliably matched to person'), plate_association_ambiguous:t('Có nhiều ứng viên biển — cần kiểm tra','Several plate candidates — needs checking'),
  plate_pairing_ambiguous:t('Camera sau thấy nhiều biển cùng lúc — không ghép','Rear camera saw several plates at once — not paired'),
  head_cut_by_frame:t('Đầu chạm mép trên khung — không xét mũ (nên đặt camera thấy trọn đầu)','Head touches top edge of frame — helmet not checked (position camera to see the whole head)')});
const COLORS = {confirmed:'bg-emerald-100 text-emerald-900', checking:'bg-slate-100 text-slate-700',
  review:'bg-amber-100 text-amber-900', error:'bg-red-100 text-red-900'};
const HEAD = (t) => ({helmet:t('Có mũ','Helmet on'), no_helmet:t('Quan sát không mũ','No helmet observed'), unknown:t('Chưa thấy rõ đầu/mũ','Head/helmet not clearly visible')});
const PLATE = (t) => ({missing:t('Chưa thấy biển','No plate seen'), reading:t('Đang đọc OCR','Reading OCR'), error:t('OCR lỗi','OCR error'),
  selecting:t('Đang chọn ảnh biển tốt nhất — chờ gần vạch','Picking the best plate image — waiting near the line'),
  candidate:t('Biển đọc thử','Candidate plate'), confirmed:t('Biển đã đối chiếu','Plate cross-checked'), partial:t('Đọc được một phần — chưa đủ toàn biển','Partly read — not the full plate'),
  unreadable:t('Chưa đọc được ký tự','Characters not readable yet'), review:t('Chưa đủ điều kiện OCR','Not ready for OCR'),
  paired:t('Biển đọc ở camera sau (ghép theo thời gian)','Plate read by rear camera (paired by time)')});

function Crop({image, label, className=''}) {
  const {lang,t}=useLang();
  const [failed,setFailed]=useState(false);
  useEffect(()=>setFailed(false),[image?.url]);
  return <figure className={`rounded-lg bg-slate-950/10 overflow-hidden ${className}`}>
    <figcaption className="px-2 py-1 text-[11px] font-semibold">{label}{image && <span className="font-normal opacity-60"> · frame {image.frame_seq}{image.timestamp && ` · ${new Date(image.timestamp).toLocaleTimeString(localeOf(lang),{hour12:false})}`}</span>}</figcaption>
    {image && !failed ? <img src={image.url} alt={t(`Ảnh ${label.toLowerCase()}`, `${label} image`)} onError={()=>setFailed(true)} className="w-full h-[calc(100%-24px)] object-contain"/> :
      <div className="flex items-center justify-center h-[calc(100%-24px)] p-2 text-xs text-center opacity-60">{failed?t('Ảnh đã hết hạn','Image expired'):t('Chưa có ảnh','No image yet')}</div>}
  </figure>;
}

function Samples({label, result}) {
  const {t}=useLang();
  return <div className="flex items-center justify-between gap-2 text-xs">
    <span>{label}</span><span className={`rounded px-2 py-1 ${COLORS[result.state] || COLORS.review}`}>
      {result.samples}/{result.required_samples} {t('mẫu','samples')} · {result.state==='confirmed'?t('Đã đối chiếu','Cross-checked'):result.state==='review'?t('Cần kiểm tra','Needs checking'):result.state==='error'?t('Lỗi model','Model error'):t('Đang kiểm tra','Checking')}
    </span>
  </div>;
}

export default function RecognitionLogPanel({gate}) {
  const {lang,t}=useLang();
  const tRef=useRef(t);
  useEffect(()=>{tRef.current=t;});
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
        if(active && !request.signal.aborted)setError(err.response?.data?.detail || tRef.current('Không tải được thẻ nhận diện.','Could not load recognition cards.'));
      } finally {if(active)timer=setTimeout(poll,1000);}
    };
    poll();return()=>{active=false;clearTimeout(timer);request?.abort();};
  },[gate,retry]);
  const cards=info?.cards || [];
  const visible=cards.filter(c=>(!track || String(c.track_id ?? '')===track || String(c.vehicle_track_id ?? '')===track)
    && c.frame_seq>(hidden[c.card_id] ?? -1));
  return <section aria-label={t('Nhận diện bằng hình ảnh','Visual recognition')} className="flex flex-col gap-3 min-h-0">
    <p className="text-xs text-white/80">{t('Đối chiếu nhiều frame của cùng track. Track ổn định chưa xác nhận danh tính học sinh; nhận diện này không phát loa.','Cross-checks several frames of the same track. A stable track does not confirm a student\'s identity; this recognition does not play announcements.')}</p>
    <details className="text-xs rounded-lg bg-white/10 p-3">
      <summary className="cursor-pointer font-semibold">{t('Model đang dùng','Models in use')} · {info?.models?.tracker?.engine || t('Đang tải','Loading')}</summary>
      <div className="space-y-1 mt-2">{['person','helmet','plate'].map(key=><p key={key} className="break-all">
        {{person:t('Người/xe','Person/bike'),helmet:t('Mũ','Helmet'),plate:t('Biển','Plate')}[key]}: {info?.models?.[key]?.family || t('Chưa có thông tin','No info')} · {info?.models?.[key]?.weights || '—'} · {info?.models?.[key]?.device || '—'}
      </p>)}<p>OCR: {info?.models?.ocr?.engine || '—'}</p></div>
    </details>
    {info?.models?.helmet?.status==='error' && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{t('Nhận diện mũ chưa khả dụng: model chưa hợp lệ.','Helmet detection unavailable: invalid model.')}</div>}
    {info?.status==='not_started' && <p role="status">{t('Pipeline chưa khởi động.','Pipeline not started.')}</p>}
    {info?.status==='stopped' && <p role="status" className="text-amber-200">{t('Pipeline đã dừng; ảnh dưới là quan sát cuối.','Pipeline stopped; images below are the last observations.')}</p>}
    {info?.gate_line_configured===false && <p role="status" className="rounded bg-amber-100 text-amber-900 p-3 text-xs">{t('Chưa cấu hình vạch cổng: vẫn hiển thị nhận diện; OCR của xe đã ghép và cảnh báo qua cổng đang chờ vạch.','Gate line not configured: recognition still shows; OCR for matched bikes and gate-crossing alerts wait for the line.')} <a href="/admin/roi" className="underline">{t('Cấu hình vùng và vạch cổng','Configure zone and gate line')}</a></p>}
    {error && <div role="alert" className="rounded bg-red-100 text-red-900 p-3 text-sm">{error} <button className="underline" onClick={()=>setRetry(v=>v+1)}>{t('Thử lại','Retry')}</button></div>}
    <div className="flex flex-wrap gap-2 text-xs">
      <input aria-label={t('Lọc track','Filter track')} placeholder={t('ID người hoặc xe','Person or bike ID')} value={track} onChange={e=>setTrack(e.target.value)} className="rounded bg-primary-container text-on-primary-container px-2 py-2 w-32"/>
      <button onClick={()=>setPaused(v=>!v)} aria-pressed={paused} className="rounded border border-white/30 px-2 py-2">{paused?t('Tiếp tục cập nhật','Resume updates'):t('Tạm dừng cập nhật','Pause updates')}</button>
      <button onClick={()=>setHidden(Object.fromEntries(cards.map(c=>[c.card_id,c.frame_seq])))} className="rounded border border-white/30 px-2 py-2">{t('Ẩn thẻ hiện tại','Hide current cards')}</button>
    </div>
    {paused && <p className="text-xs text-amber-200">{t('Đang tạm dừng cập nhật thẻ; camera vẫn chạy.','Card updates paused; camera is still running.')}</p>}
    <div className="space-y-3 overflow-y-auto max-h-[70vh] pr-1" data-testid="recognition-cards">
      {!visible.length && <p role="status" className="text-sm bg-primary-container text-on-primary-container rounded p-3">{!info && !error?t('Đang tải nhận diện…','Loading recognition…'):track?t('Không có thẻ phù hợp bộ lọc.','No cards match the filter.'):t('Chưa có đối tượng mới trong vùng nhận diện.','No new objects in the recognition zone yet.')}</p>}
      {visible.map(card=><article key={card.card_id} data-testid="recognition-card" className="rounded-xl bg-primary-container text-on-primary-container p-3 space-y-3 border border-white/15">
        <header className="flex justify-between gap-2"><div><p className="font-semibold">{card.kind==='plate' ? t('Biển số chưa ghép xe','Plate not matched to a bike') : `${t('Người','Person')} #${card.track_id ?? t('chưa có ID','no ID yet')}`}</p><p className="text-[11px] opacity-70">{card.camera_id}{card.vehicle_track_id!=null && ` · ${t('Xe','Bike')} #${card.vehicle_track_id}`}</p></div><time className="text-xs">{new Date(card.last_seen).toLocaleTimeString(localeOf(lang),{hour12:false})}</time></header>
        {card.kind==='plate' ? <Crop image={card.images?.plate} label={t('Biển số','Plate')} className="h-[150px]"/> : <>
        <div className="grid grid-cols-[.8fr_1.2fr] gap-2">
          <Crop image={card.images?.person} label={t('Người','Person')} className="row-span-2 h-[218px]"/>
          <Crop image={card.images?.head} label={t('Đầu / mũ','Head / helmet')} className="h-[105px]"/>
          <Crop image={card.images?.plate} label={t('Biển số','Plate')} className="h-[105px]"/>
        </div>
        <Samples label={t('Theo dõi người','Person tracking')} result={card.person}/>
        <Samples label={HEAD(t)[card.helmet.value] || HEAD(t).unknown} result={card.helmet}/>
        </>}
        <div className={`rounded-lg px-3 py-2 text-xs ${['confirmed','paired'].includes(card.plate.state)?COLORS.confirmed:card.plate.state==='error'?COLORS.error:COLORS.review}`}>
          <p className="font-semibold">{PLATE(t)[card.plate.state] || t('Biển cần kiểm tra','Plate needs checking')}</p>
          {card.plate.text && <p className="font-mono text-lg mt-1 tracking-wide">{card.plate.text}</p>}
          <p>{card.plate.state==='paired' ? t('Xe máy không có biển trước — lấy biển camera sau xác nhận cùng lúc','Motorbike has no front plate — using the rear-camera plate seen at the same time') : card.plate_debug?.max_attempts ? t(`${card.plate_debug.attempts}/1 lượt OCR · chọn một crop tốt nhất`,`${card.plate_debug.attempts}/1 OCR attempts · picking the single best crop`) : card.vehicle_track_id==null ? t('Chưa ghép xe — chưa thực hiện OCR','No bike matched — OCR not run') : t('0/1 lượt OCR · chờ crop biển phù hợp','0/1 OCR attempts · waiting for a suitable plate crop')}</p>
          {card.plate_debug?.best_frame_id != null && <div className="mt-2 space-y-1">
            <p>{t('Ảnh chọn:','Selected image:')} frame {card.plate_debug.best_frame_id} · {card.plate_debug.size?.join('×')} {t('px gốc','px original')}</p>
            <p>{t('Chất lượng crop:','Crop quality:')} {card.plate_debug.quality} · {t('độ nét:','sharpness:')} {card.plate_debug.blur}</p>
            <p>Confidence box: {card.plate_debug.detector_confidence} · {t('tương phản:','contrast:')} {card.plate_debug.contrast}</p>
            <p>{t('Trạng thái:','Status:')} {card.plate_debug.status}{card.plate_debug.technical_retries>0 && ` · ${t('thử lại do lỗi kỹ thuật:','retries after technical errors:')} ${card.plate_debug.technical_retries}`}</p>
            <a href={`/guard/plate_best/${card.ocr_track_id ?? card.vehicle_track_id}?gate=${encodeURIComponent(gate)}&epoch=${card.source_epoch}`} className="underline" download>{t('Tải ảnh biển đã chọn','Download selected plate image')}</a>
            <details><summary className="cursor-pointer">{t('Chi tiết OCR','OCR details')}</summary>
              <p>{t('Dòng trên:','Top line:')} {card.plate_debug.raw_top || '—'}</p><p>{t('Dòng dưới:','Bottom line:')} {card.plate_debug.raw_bottom || '—'}</p>
              <p>{t('Toàn biển:','Full plate:')} {card.plate_debug.normalized || t('Chưa đọc đủ','Not fully read')}</p>
            </details>
          </div>}
          {card.riding?.state && <p className="mt-2">{t('Hành vi:','Behaviour:')} {card.riding.state==='RIDING'?t('Đang đi xe','Riding'):card.riding.state==='WALKING_WITH_BIKE'?t('Dắt xe','Walking the bike'):t('Chưa xác định','Undetermined')} · {t('chân:','legs:')} {card.riding.leg_status==='AVAILABLE'?t('quan sát được','visible'):t('không đủ quan sát','not visible enough')}</p>}
          {card.riding?.state && <details><summary className="cursor-pointer">{t('Chi tiết tư thế','Pose details')}</summary>
            <p>Hip: {card.riding.hip_score ?? t('Không quan sát được','Not observed')} · torso: {card.riding.torso_score ?? t('Không quan sát được','Not observed')}</p>
            <p>Overlap: {card.riding.overlap ?? '—'} · temporal: {card.riding.temporal ?? '—'} · motion: {card.riding.motion ?? '—'}</p>
            <p>Score: {card.riding.score ?? '—'} · {t('chân:','legs:')} {card.riding.leg_status}</p>
          </details>}
          {card.plate.association==='unverified' && <p className="mt-1 font-semibold">{t('Chưa ghép xe — không gán học sinh','No bike matched — no student assigned')}</p>}
          {card.plate.association==='paired_camera' && <p className="mt-1">{t('Ghép theo thời gian: chỉ đúng khi mỗi lần một xe qua cổng','Paired by time: only correct when one bike passes the gate at a time')}</p>}
        </div>
        {card.reasons?.length>0 && <p className="text-[11px] opacity-80">{card.reasons.map(r=>REASONS(t)[r] || r).join(' · ')}</p>}
        {card.images_state==='error' && <p role="alert" className="text-xs text-red-800">{t('Không tạo được ảnh crop; kết quả nhận diện cần kiểm tra.','Could not create crop images; recognition result needs checking.')}</p>}
      </article>)}
    </div>
  </section>;
}
