import { speakableIssues } from './alertFilter.js';

export function buildAlertMessage(data, lang = 'vi') {
  const t=(vi,en)=>(lang==='en'?en:vi);
  const codes = new Set(speakableIssues(data));
  const helmet=codes.has('NO_HELMET'), riding=codes.has('RIDING_THROUGH_GATE');
  const parts=[];
  if(helmet && riding) parts.push(t('Không đội mũ, vui lòng dắt xe.','No helmet, please walk your bike.'));
  else if(helmet) parts.push(t('Vui lòng đội mũ.','Please wear a helmet.'));
  else if(riding) parts.push(t('Vui lòng dắt xe.','Please walk your bike.'));
  for(const [code,text] of [['MISSING_MIRROR',t('Mời kiểm tra gương trái.','Please check the left mirror.')],
    ['TOO_MANY_RIDERS',t('Mời kiểm tra số người trên xe.','Please check the number of riders.')],
    ['PLATE_NOT_REGISTERED',t('Mời kiểm tra đăng ký xe.','Please check the bike registration.')]]) {
    if(codes.has(code))parts.push(text);
  }
  // A gate pass (no violation) still announces its plate: one sentence per
  // bike, plate first, then whatever is wrong.
  const pass=data.type==='gate_pass';
  if(!parts.length && !codes.has('PLATE_UNREADABLE') && !pass)return '';
  const match=(data.plate_read || '').match(/^(\d{2})([A-Z]\d?|[A-Z]{2})(\d{4,5})$/);
  const plateValid=data.plate_status==='CONFIRMED' || (data.plate_status==null && data.plate_format_valid===true);
  if(match && plateValid)parts.unshift(`${match[1]} ${match[2]} ${match[3].slice(0,-2)} ${match[3].slice(-2)}.`);
  else parts.unshift(t('Không đọc được biển số.','Plate unreadable.'));
  return parts.join(' ');
}

export function createAlertAudio({beep, speak, cancel, config={rate:1.30,volume:1}, dedupKeys=new Set(), lang='vi',
  now=Date.now, setTimer=setTimeout, clearTimer=clearTimeout}) {
  const spoken=dedupKeys, batches=new Map(), timers=new Set();
  let disposed=false, settings=config;
  const schedule=(fn,delay)=>{
    const id=setTimer(()=>{timers.delete(id);if(!disposed)fn();},delay);
    timers.add(id);return id;
  };
  const keyFor=data=>data.crossing_event_id!=null
    ? `${data.gate_id || ''}:${data.camera_id || ''}:${data.source_epoch ?? ''}:${data.vehicle_track_id ?? data.track_id}:${data.crossing_event_id}`
    : data.event_id || data.encounter_id || `${data.gate_id}:${data.source_epoch}:${data.track_id ?? data.timestamp}`;
  return {
    configure(value){settings={...settings,...value};},
    accept(data){
      if(disposed || !data || data.replayed || data.historical || data.type==='gate_crossed' || data.alert_finalized===false)return;
      const ts=Date.parse(data.confirmed_at || data.timestamp);
      if(Number.isFinite(ts) && now()-ts>5000)return;
      const codes=speakableIssues(data);
      const pass=data.type==='gate_pass' && data.audio_authorized!==false;
      if(!codes.length && !pass)return;
      const key=keyFor(data);
      if(spoken.has(key))return;
      if(batches.has(key)) {
        const batch=batches.get(key);
        const issues=new Map((batch.data.issues || []).map(i=>[i.code,i]));
        for(const issue of data.issues || [])issues.set(issue.code,issue);
        batch.data={...batch.data,...data,issues:[...issues.values()]};return;
      }
      if(batches.size>=2){
        const oldest=batches.keys().next().value;
        clearTimer(batches.get(oldest).timer);timers.delete(batches.get(oldest).timer);batches.delete(oldest);
      }
      const batch={data:{...data},received:now()};batches.set(key,batch);
      const dispatch=()=>{
        batches.delete(key);
        if(now()-batch.received>5000 || spoken.has(key))return;
        const text=buildAlertMessage(batch.data,lang);
        if(!text)return;
        spoken.add(key);
        while(spoken.size>4096)spoken.delete(spoken.values().next().value);
        const delay=beep(speakableIssues(batch.data)[0] || 'GATE_PASS') || 0;
        if(settings.debug)console.debug('[Alert]',{event:key,plate:batch.data.plate_read,
          issues:speakableIssues(batch.data),message:text,beep_calls:1,tts_calls:0,stage:'beep_requested'});
        schedule(()=>{
          if(now()-batch.received>5000)return;
          speak(text,{rate:settings.rate,pitch:1,volume:settings.volume});
          if(settings.debug)console.debug('[Alert]',{event:key,beep_calls:1,tts_calls:1,stage:'speech_requested'});
        },delay);
      };
      // Schema v2 is already sealed at crossing. Legacy producers get one
      // brief coalescing window but never a second audio job for late issues.
      if(data.alert_finalized===true)dispatch();
      else batch.timer=schedule(dispatch,300);
    },
    dispose(){disposed=true;for(const id of timers)clearTimer(id);timers.clear();batches.clear();cancel();},
  };
}
