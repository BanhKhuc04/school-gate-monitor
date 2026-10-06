#!/usr/bin/env python
"""Same sanitizer as sanitize_landing.py but for operations.html."""
import re
from pathlib import Path

PATH = Path('marketing/operations.html')
ICON = {
    'verified':'✅','calendar_today':'📅','menu':'☰','shield':'🛡','video_camera_front':'📷',
    'directions_bike':'🚲','badge':'🪪','visibility':'👁','person':'🧑','groups':'👥',
    'analytics':'📊','science':'🔬','description':'📄','admin_panel_settings':'⚙️',
    'check_circle':'✅','pending':'⏳','priority_high':'❗','schedule':'🕒','school':'🏫',
    'face':'🙂','play_circle':'▶','refresh':'↻','speed':'⏱','gavel':'⚖','download':'⬇',
    'upload':'⬆','bolt':'⚡','local_police':'🛡','login':'➡','logout':'⇤','edit':'✎',
    'delete':'🗑','add':'＋','close':'✕','search':'🔍','check':'✓','arrow_back':'←',
    'chevron_right':'›','expand_more':'⌄','warning':'⚠','info':'ⓘ','error':'✕',
    'image':'🖼','videocam':'📹','mic':'🎤','volume_up':'🔊','volume_off':'🔇',
    'home':'⌂','settings':'⚙','memory':'🧠','folder':'📁','build':'🛠','wifi':'📶',
    'wifi_off':'⛔','router':'📡','database':'🗄','lock':'🔒','lock_open':'🔓','key':'🔑',
    'event':'📅','star':'★','thumb_up':'👍','thumb_down':'👎','flag':'⚑',
    'chevron_left':'‹','arrow_forward':'→','arrow_downward':'↓','arrow_upward':'↑',
    'notifications_active':'🔔','hearing':'👂','campaign':'📣','support_agent':'•',
    'fact_check':'✓','security':'🛡','cloud_done':'☁','grade':'★','block':'🚫',
    'storefront':'🏪','directions_car':'🚗','public':'🌐','vpn_lock':'🔒','room':'🏠',
    'maps_home_work':'🏠','location_on':'📍','thermostat':'🌡','straighten':'📏',
    'timer':'⏲','devices':'📱','fiber_manual_record':'⏺','crisis_alert':'❗','sync':'↻',
    'light_mode':'☀','dark_mode':'🌙','speaker_notes':'📝','help':'❓','dashboard':'▦',
    'report':'📊','inventory_2':'📦','verified_user':'✅','construction':'🚧',
    'engineering':'🔧','rule':'📏','task':'☑','logout_alt':'⇤',
    'switch_access_shortcut':'⌨','toggle_on':'⚪','toggle_off':'⊗',
    'workspaces':'', 'topic':'', 'memory_alt':'🧠',
}

src = PATH.read_text(encoding='utf-8')

def sub_icon(m):
    name = m.group(2)
    cls_extra = m.group(1).replace('material-symbols-outlined', '').strip()
    e = ICON.get(name, '•')
    cls = ('material-icon ' + cls_extra).strip()
    return f'<span class="{cls}">{e}</span>'

src = re.sub(r'<span class="(material-symbols-outlined[^"]*)">([a-z_]+)</span>',
             sub_icon, src)

# Replace alert() with a title-only honest hint.
src = re.sub(
    r'onclick="alert\(([^)]*)\);"',
    'title="(chỉ minh họa — chưa nối backend)"',
    src)

PATH.write_text(src, encoding='utf-8')
print('operations.html rewritten:', PATH)