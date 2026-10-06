import test from 'node:test';
import assert from 'node:assert/strict';
import {createAlertAudio, buildAlertMessage} from '../src/utils/alertAudio.js';

function harness() {
  let clock=1000, id=0;
  const timers=new Map(), beeps=[], speech=[];
  const audio=createAlertAudio({beep:code=>{beeps.push(code);return 200;},
    speak:(text,options)=>speech.push({text,options}), cancel:()=>{}, now:()=>clock,
    config:{rate:1.32,volume:.95}, setTimer:(fn,delay)=>{timers.set(++id,{fn,at:clock+delay});return id;},clearTimer:id=>timers.delete(id)});
  const advance=ms=>{clock+=ms;for(const [id,t] of [...timers])if(t.at<=clock){timers.delete(id);t.fn();}};
  const event={event_id:'e1', crossing_event_id:'c1', vehicle_track_id:7, alert_finalized:true,
    evidence_state:'persisted', plate_status:'CONFIRMED',plate_read:'89F123792',
    issues:[{code:'NO_HELMET',status:'confirmed'},{code:'RIDING_THROUGH_GATE',status:'confirmed'}]};
  return {audio,beeps,speech,advance,event};
}

test('two issues produce one beep and one configured utterance with plate first',()=>{
  const h=harness();h.audio.accept(h.event);h.advance(300);
  assert.equal(h.beeps.length,1);assert.equal(h.speech.length,1);
  assert.equal(h.speech[0].text,'89 F1 237 92. Không đội mũ, vui lòng dắt xe.');
  assert.equal(h.speech[0].options.rate,1.32);assert.equal(h.speech[0].options.volume,.95);
});
test('unreadable alone and three faults each produce one short audio job',()=>{
  const h=harness();const e={...h.event,plate_read:'',plate_status:'UNREADABLE',issues:[...h.event.issues,{code:'PLATE_UNREADABLE',status:'confirmed'}]};
  h.audio.accept(e);h.advance(300);
  assert.equal(h.speech[0].text,'Không đọc được biển số. Không đội mũ, vui lòng dắt xe.');
  assert.equal(h.beeps.length,1);
  h.audio.accept({...e,crossing_event_id:'c2',issues:[{code:'PLATE_UNREADABLE',status:'confirmed'}]});h.advance(300);
  assert.equal(h.speech[1].text,'Không đọc được biển số.');
});
test('duplicate or late issue on sealed key never produces another beep/TTS',()=>{
  const h=harness();h.audio.accept(h.event);h.advance(300);
  h.audio.accept({...h.event,event_version:2,issues:[{code:'PLATE_UNREADABLE',status:'confirmed'}]});h.advance(300);
  assert.equal(h.beeps.length,1);assert.equal(h.speech.length,1);
});
test('no faults, unsealed crossing notice, and failed evidence are silent',()=>{
  const h=harness();h.audio.accept({...h.event,issues:[]});h.audio.accept({type:'gate_crossed',track_id:7});
  h.audio.accept({...h.event,alert_finalized:false});h.audio.accept({...h.event,evidence_state:'failed'});h.advance(1000);
  assert.equal(h.beeps.length,0);assert.equal(h.speech.length,0);
});
test('message formatter follows short single-issue examples',()=>{
  assert.equal(buildAlertMessage({plate_read:'89F123792',plate_status:'CONFIRMED',issues:[{code:'NO_HELMET',status:'confirmed'}]}),'89 F1 237 92. Vui lòng đội mũ.');
});
