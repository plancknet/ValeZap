(() => {
    const form = document.getElementById('chat-form');
    const textarea = document.getElementById('chat-message');
    const sendButton = document.getElementById('send-button');
    const messagesWrapper = document.getElementById('messages-wrapper');
    const placeholder = document.getElementById('placeholder-state');
    const debugBar = document.getElementById('debug-bar');
    const statusIndicator = document.getElementById('status-indicator');
    const sessionInfo = document.getElementById('session-info');

    const renderedMessages = new Set();

    const params = new URLSearchParams(window.location.search);
    const storedPlayer = localStorage.getItem('valezap_player_id');

    const generateId = () => {
        if (window.crypto && window.crypto.randomUUID) {
            return window.crypto.randomUUID();
        }
        return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
            const r = (Math.random() * 16) | 0;
            const v = c === 'x' ? r : (r & 0x3) | 0x8;
            return v.toString(16);
        });
    };

    let playerId = params.get('player') || storedPlayer || generateId();
    if (!params.get('player')) {
        localStorage.setItem('valezap_player_id', playerId);
    }

    let sessionId = sessionStorage.getItem('valezap_session_id');
    if (!sessionId) {
        sessionId = generateId();
        sessionStorage.setItem('valezap_session_id', sessionId);
    }

    const scrollToBottom = () => {
        const container = document.getElementById('messages-panel');
        container.scrollTo({ top: container.scrollHeight, behavior: 'smooth' });
    };

    const formatTime = (timestamp) => {
        try {
            const date = timestamp ? new Date(timestamp) : new Date();
            return date.toLocaleTimeString('pt-BR', {
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch (error) {
            return '';
        }
    };

    const renderMessage = (message) => {
        if (!message || !message.message) {
            return;
        }
        const key = message.id || `${message.session_id}-${message.player_id}-${message.message}-${message.created_at}`;
        if (renderedMessages.has(key)) {
            return;
        }
        renderedMessages.add(key);

        placeholder.style.display = 'none';
        const group = document.createElement('div');
        group.className = `message-group ${message.is_from_user ? 'user' : 'bot'}`;

        const card = document.createElement('div');
        card.className = 'message-card';

        const text = document.createElement('p');
        text.className = 'message-text';
        text.textContent = message.message;
        card.appendChild(text);

        const meta = document.createElement('span');
        meta.className = 'message-metadata';
        meta.textContent = formatTime(message.created_at);
        card.appendChild(meta);

        group.appendChild(card);
        messagesWrapper.appendChild(group);
        scrollToBottom();
    };

    const refreshDebug = () => {
        debugBar.textContent = `Session ID: ${sessionId} | Player ID: ${playerId}`;
        sessionInfo.textContent = `Sessão ${sessionId.slice(0, 8)} · Player ${playerId.slice(0, 8)}`;
    };

    refreshDebug();

    const toggleSendingState = (isSending) => {
        if (isSending) {
            sendButton.setAttribute('aria-busy', 'true');
            sendButton.disabled = true;
            statusIndicator.textContent = 'Enviando...';
        } else {
            sendButton.removeAttribute('aria-busy');
            statusIndicator.textContent = 'Online';
        }
    };

    const clientKey = form.dataset.clientKey || '';

    const sendMessage = async (content) => {
        const sanitized = content.trim();
        if (!sanitized) {
            return;
        }

        const userMessage = {
            id: generateId(),
            session_id: sessionId,
            player_id: playerId,
            message: sanitized,
            is_from_user: true,
            created_at: new Date().toISOString(),
        };
        renderMessage(userMessage);

        toggleSendingState(true);
        try {
            const response = await fetch('/functions/v1/webhook-valezap', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'x-api-key': clientKey,
                },
                body: JSON.stringify({
                    sessao: sessionId,
                    player: playerId,
                    mensagem: sanitized,
                }),
            });

            if (!response.ok) {
                throw new Error('Falha ao enviar mensagem');
            }

            const payload = await response.json().catch(() => ({}));
            if (payload?.reply && payload.reply.message) {
                renderMessage(payload.reply);
            }
        } catch (error) {
            console.error(error);
            renderMessage({
                id: generateId(),
                session_id: sessionId,
                player_id: playerId,
                message: 'Não consegui enviar sua mensagem. Tente novamente em instantes.',
                is_from_user: false,
                created_at: new Date().toISOString(),
            });
        } finally {
            toggleSendingState(false);
        }
    };

    const loadHistory = async () => {
        try {
            const response = await fetch(`/api/messages?sessao=${encodeURIComponent(sessionId)}&player=${encodeURIComponent(playerId)}`);
            if (!response.ok) {
                return;
            }
            const data = await response.json();
            if (Array.isArray(data.messages) && data.messages.length) {
                data.messages.forEach(renderMessage);
            }
        } catch (error) {
            console.warn('Histórico indisponível', error);
        }
    };

    const connectStream = () => {
        const streamUrl = `/api/messages/stream?sessao=${encodeURIComponent(sessionId)}&player=${encodeURIComponent(playerId)}`;
        const source = new EventSource(streamUrl);

        source.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data && data.message) {
                    renderMessage(data);
                }
            } catch (error) {
                console.error('Erro ao processar mensagem SSE', error);
            }
        };

        source.onerror = () => {
            statusIndicator.textContent = 'Reconectando...';
            source.close();
            setTimeout(connectStream, 4000);
        };

        source.onopen = () => {
            statusIndicator.textContent = 'Online';
        };
    };

    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
        sendButton.disabled = textarea.value.trim().length === 0;
    });

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        const value = textarea.value;
        textarea.value = '';
        textarea.style.height = 'auto';
        sendButton.disabled = true;
        sendMessage(value);
    });

    loadHistory().then(connectStream);
})();