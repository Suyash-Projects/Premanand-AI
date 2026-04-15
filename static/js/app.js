document.addEventListener('DOMContentLoaded', () => {
    initParticles();
    
    const form = document.getElementById('qa-form');
    const input = document.getElementById('query-input');
    const chatContainer = document.getElementById('chat-container');
    const landingState = document.getElementById('landing-state');
    const chatState = document.getElementById('chat-state');
    const seedDataBtn = document.getElementById('seedDataBtn');

    let state = 'landing'; // 'landing' | 'chat'

    seedDataBtn.addEventListener('click', async () => {
        seedDataBtn.innerText = "Loading...";
        seedDataBtn.disabled = true;
        try {
            const res = await fetch('/api/process-video/demo', { method: 'POST' });
            const data = await res.json();
            seedDataBtn.innerText = "Demo Loaded ✔";
            setTimeout(() => seedDataBtn.style.display = 'none', 2000);
        } catch(e) {
            seedDataBtn.innerText = "Error";
            console.error(e);
        }
    });

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        const query = input.value.trim();
        if(!query) return;

        if(state === 'landing') {
            landingState.classList.add('hidden');
            chatState.classList.remove('hidden');
            state = 'chat';
        }

        // Add user msg
        appendMessage(query, 'user');
        input.value = '';

        // Add loading state
        const loadingId = appendMessage('<span class="loading-dots">उत्तर खोजा जा रहा है</span>', 'ai');

        try {
            const response = await fetch('/api/ask', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query })
            });
            const data = await response.json();
            
            // Remove loader
            document.getElementById(loadingId).remove();

            // Append answer
            let formattedResponse = `
                <div class="whitespace-pre-wrap">${data.answer}</div>
            `;
            
            if(data.reference && data.reference.video_url) {
                const vidUrl = new URL(data.reference.video_url);
                const vidId = vidUrl.searchParams.get('v') || data.reference.video_url.split('/').pop();
                const timeStr = formatTime(data.reference.timestamp);
                const thumbUrl = `https://img.youtube.com/vi/${vidId}/mqdefault.jpg`;
                const fullLink = `${data.reference.video_url}&t=${data.reference.timestamp}s`;

                formattedResponse += `
                <div class="mt-4 border-t border-saffron-500/30 pt-4 flex flex-col sm:flex-row gap-4 items-start sm:items-center">
                    <a href="${fullLink}" target="_blank" class="relative group block overflow-hidden rounded-lg shadow-lg border border-slate-700 hover:border-saffron-500 transition-colors w-40 shrink-0">
                        <img src="${thumbUrl}" alt="Video Thumbnail" class="w-full h-auto group-hover:scale-105 transition-transform duration-300">
                        <div class="absolute inset-0 bg-black/40 group-hover:bg-black/10 transition-colors flex items-center justify-center">
                            <div class="bg-red-600 rounded-full w-8 h-8 flex items-center justify-center shadow-lg">
                                <svg class="w-4 h-4 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                            </div>
                        </div>
                    </a>
                    <div class="text-sm">
                        <div class="text-gray-400 mb-1">Source Video</div>
                        <a href="${fullLink}" target="_blank" class="text-saffron-400 hover:text-saffron-300 transition-colors inline-flex items-center gap-1 font-semibold">
                            Watch from ${timeStr}
                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"></path></svg>
                        </a>
                    </div>
                </div>`;
            }

            appendMessage(formattedResponse, 'ai', true);

        } catch(err) {
            document.getElementById(loadingId).remove();
            appendMessage('<span class="text-red-400">क्षमा करें, सर्वर से संपर्क नहीं हो पाया।</span>', 'ai');
        }
    });

    function appendMessage(htmlContent, sender, isHTML = false) {
        const id = 'msg-' + Date.now();
        const wrapper = document.createElement('div');
        wrapper.id = id;
        wrapper.className = `flex flex-col gap-1 w-full max-w-[85%] animate-fade-in-up ${sender === 'user' ? 'self-end items-end' : 'self-start items-start'}`;

        const label = document.createElement('span');
        label.className = `text-xs px-2 ${sender === 'user' ? 'text-gray-400' : 'text-saffron-400'}`;
        label.innerText = sender === 'user' ? 'You' : 'Premanand AI';

        const bubble = document.createElement('div');
        bubble.className = `p-4 shadow-lg font-hindi text-lg font-medium tracking-wide ${
            sender === 'user' 
            ? 'bg-saffron-600/90 text-white rounded-2xl rounded-tr-sm border border-saffron-500/50' 
            : 'bg-slate-800/80 backdrop-blur-md text-gray-200 rounded-2xl rounded-tl-sm border border-saffron-500/20'
        }`;

        if(isHTML) {
            bubble.innerHTML = htmlContent;
        } else {
            bubble.innerHTML = htmlContent; 
        }

        wrapper.appendChild(label);
        wrapper.appendChild(bubble);
        chatContainer.appendChild(wrapper);

        // Smooth scroll to bottom
        chatState.scrollTop = chatState.scrollHeight;
        
        return id;
    }

    function formatTime(seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if(h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    function initParticles() {
        const pContainer = document.getElementById('particles');
        const count = 15;
        for(let i=0; i<count; i++) {
            const p = document.createElement('div');
            p.className = 'particle';
            const size = Math.random() * 8 + 2;
            p.style.width = size + 'px';
            p.style.height = size + 'px';
            p.style.left = Math.random() * 100 + 'vw';
            p.style.top = Math.random() * 100 + 'vh';
            p.style.setProperty('--duration', (Math.random() * 10 + 10) + 's');
            p.style.setProperty('--delay', (Math.random() * 5) + 's');
            p.style.opacity = Math.random() * 0.5 + 0.1;
            pContainer.appendChild(p);
        }
    }
});
