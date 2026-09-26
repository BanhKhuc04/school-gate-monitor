/**
 * Guard page JavaScript
 * - Kết nối WebSocket /guard/ws
 * - Hiện banner đỏ khi có cảnh báo
 * - Phát tiếng beep bằng Web Audio API
 */

(function() {
    'use strict';
    
    // WebSocket connection
    let ws = null;
    let bannerTimeout = null;
    
    // Web Audio API context (lazy init on first beep)
    let audioCtx = null;
    
    function initAudio() {
        if (!audioCtx) {
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        }
        return audioCtx;
    }
    
    function playBeep() {
        try {
            const ctx = initAudio();
            
            // Tạo oscillator cho tiếng beep
            const oscillator = ctx.createOscillator();
            const gainNode = ctx.createGain();
            
            // Cấu hình
            oscillator.type = 'sine';
            oscillator.frequency.value = 800; // 800Hz
            gainNode.gain.value = 0.3; // Volume 30%
            
            // Kết nối: oscillator -> gain -> output
            oscillator.connect(gainNode);
            gainNode.connect(ctx.destination);
            
            // Chạy 200ms
            oscillator.start(ctx.currentTime);
            oscillator.stop(ctx.currentTime + 0.2);
            
            console.log('[Guard] Beep played');
        } catch (e) {
            console.error('[Guard] Audio error:', e);
        }
    }
    
    function showBanner(violationType) {
        // Tìm hoặc tạo banner
        let banner = document.getElementById('alert-banner');
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'alert-banner';
            banner.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background-color: #dc3545;
                color: white;
                padding: 15px 20px;
                text-align: center;
                font-size: 18px;
                font-weight: bold;
                z-index: 1000;
                display: none;
            `;
            document.body.insertBefore(banner, document.body.firstChild);
        }
        
        // Hiện banner với nội dung
        banner.textContent = '⚠️ CẢNH BÁO: ' + violationType;
        banner.style.display = 'block';
        
        // Xóa timeout cũ nếu có
        if (bannerTimeout) {
            clearTimeout(bannerTimeout);
        }
        
        // Tự ẩn sau 3 giây
        bannerTimeout = setTimeout(function() {
            banner.style.display = 'none';
        }, 3000);
        
        console.log('[Guard] Banner shown:', violationType);
    }
    
    function connectWebSocket() {
        // Determine WebSocket protocol (ws or wss)
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = protocol + '//' + window.location.host + '/guard/ws';
        
        console.log('[Guard] Connecting to WebSocket:', wsUrl);
        
        ws = new WebSocket(wsUrl);
        
        ws.onopen = function() {
            console.log('[Guard] WebSocket connected');
        };
        
        ws.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                console.log('[Guard] Received alert:', data);
                
                // Hiện banner
                showBanner(data.violation_type);
                
                // Phát beep
                playBeep();
                
            } catch (e) {
                console.error('[Guard] Error parsing message:', e);
            }
        };
        
        ws.onerror = function(error) {
            console.error('[Guard] WebSocket error:', error);
        };
        
        ws.onclose = function() {
            console.log('[Guard] WebSocket disconnected');
            // Thử kết nối lại sau 3 giây
            setTimeout(connectWebSocket, 3000);
        };
    }
    
    // Khởi động khi DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', connectWebSocket);
    } else {
        connectWebSocket();
    }
})();
