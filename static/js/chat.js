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
    const pendingMessages = [];
    let sequencedMode = false;
    let waitingForReply = false;

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

    const escapeHtml = (value) =>
        String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');

    const applyInlineFormats = (escaped) => {
        const segments = escaped.split(/`([^`]+)`/g);
        let composed = '';
        segments.forEach((segment, index) => {
            if (index % 2 === 1) {
                composed += `<code>${segment}</code>`;
            } else {
                let formatted = segment
                    .replace(/\*([^*\s][^*]*?)\*/g, '<strong>$1</strong>')
                    .replace(/_([^_\s][^_]*?)_/g, '<em>$1</em>')
                    .replace(/~([^~]+)~/g, '<s>$1</s>')
                    .replace(/
?
/g, '<br>');
                composed += formatted;
            }
        });
        return composed;
    };

    const formatMessageText = (raw) => {
        if (!raw) {
            return '';
        }
        const parts = String(raw).split(/```([\s\S]*?)```/g);
        let result = '';
        parts.forEach((part, index) => {
            if (index % 2 === 1) {
                const code = escapeHtml(part).replace(/
/g, '').replace(/
/g, '<br>');
                result += `<pre class="message-preformatted">${code}</pre>`;
            } else {
                const escaped = escapeHtml(part);
                result += applyInlineFormats(escaped);
            }
        });
        return result;
    };

    const getMessageKey = (message) => {
        if (!message) {
            return '';
        }
        if (message.id) {
            return String(message.id);
        }
        return `${message.session_id}-${message.player_id}-${message.message}-${message.created_at}`;
    };

    const findPendingByTempId = (tempId) => pendingMessages.find((entry) => entry.tempId === tempId);

    const findPendingMatch = (message) => {
        if (!message || !message.message) {
            return undefined;
        }
        const text = String(message.message).trim();
        return pendingMessages.find(
            (entry) =>
                entry.text === text &&
                entry.session_id === message.session_id &&
                entry.player_id === message.player_id
        );
    };

    const removePendingEntry = (entry) => {
        const index = pendingMessages.indexOf(entry);
        if (index !== -1) {
            pendingMessages.splice(index, 1);
        }
    };

    const registerPendingMessage = (message, element) => {
        const entry = {
            tempId: message.id || null,
            key: getMessageKey(message),
            text: (message.message || '').trim(),
            session_id: message.session_id,
            player_id: message.player_id,
            element,
        };
        pendingMessages.push(entry);
        return entry;
    };

    const replacePendingMessage = (entry, finalMessage) => {
        if (!entry || !finalMessage) {
            return;
        }
        const newKey = getMessageKey(finalMessage);
        renderedMessages.delete(entry.key);
        renderedMessages.add(newKey);

        const element = entry.element;
        if (element) {
            element.dataset.messageId = finalMessage.id || '';
            element.className = `message-group ${finalMessage.is_from_user ? 'user' : 'bot'}`;
            const textNode = element.querySelector('.message-text');
            if (textNode) {
                textNode.innerHTML = formatMessageText(finalMessage.message);
            }
            const metaNode = element.querySelector('.message-metadata');
            if (metaNode) {
                metaNode.textContent = formatTime(finalMessage.created_at);
            }
        }
        removePendingEntry(entry);
    };

    const allowNextMessage = () => {
        if (!sequencedMode || !waitingForReply) {
            return;
        }
        waitingForReply = false;
        toggleSendingState(false);
    };

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

    let playerId = params.get('player') || storedPlayer || generateId();
    if (!params.get('player')) {
        localStorage.setItem('valezap_player_id', playerId);
    }

    let sessionId = sessionStorage.getItem('valezap_session_id');
    if (!sessionId) {
        sessionId = generateId();
        sessionStorage.setItem('valezap_session_id', sessionId);
    }

    const renderMessage = (message) => {
        if (!message || !message.message) {
            return null;
        }
        const key = getMessageKey(message);
        if (renderedMessages.has(key)) {
            return null;
        }
        renderedMessages.add(key);

        placeholder.style.display = 'none';
        const group = document.createElement('div');
        group.className = `message-group ${message.is_from_user ? 'user' : 'bot'}`;
        group.dataset.messageId = message.id || '';

        const card = document.createElement('div');
        card.className = 'message-card';

        const text = document.createElement('p');
        text.className = 'message-text';
        text.innerHTML = formatMessageText(message.message);
        card.appendChild(text);

        const meta = document.createElement('span');
        meta.className = 'message-metadata';
        meta.textContent = formatTime(message.created_at);
        card.appendChild(meta);

        group.appendChild(card);
        messagesWrapper.appendChild(group);
        scrollToBottom();
        return group;
    };

    const refreshDebug = () => {
        debugBar.textContent = `Session ID: ${sessionId} | Player ID: ${playerId}`;
        sessionInfo.textContent = `Sessao ${sessionId.slice(0, 8)} - Player ${playerId.slice(0, 8)}`;
    };

    refreshDebug();

    const toggleSendingState = (isSending) => {
        if (isSending) {
            sendButton.setAttribute('aria-busy', 'true');
            sendButton.disabled = true;
            statusIndicator.textContent = 'Enviando...';
        } else {
            sendButton.removeAttribute('aria-busy');
            sendButton.disabled = waitingForReply || textarea.value.trim().length === 0;
            statusIndicator.textContent = waitingForReply ? 'Aguardando resposta...' : 'Online';
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
        const pendingElement = renderMessage(userMessage);
        let pendingEntry = null;
        if (pendingElement) {
            pendingEntry = registerPendingMessage(userMessage, pendingElement);
        }

        waitingForReply = true;

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
            const record = payload?.data?.record;
            if (record && record.message) {
                const existingEntry = findPendingByTempId(userMessage.id) || findPendingMatch(record);
                if (existingEntry) {
                    replacePendingMessage(existingEntry, record);
                } else {
                    renderMessage(record);
                }
            }
            if (payload?.reply && payload.reply.message) {
                const replyMessage = { ...payload.reply, is_from_user: false };
                renderMessage(replyMessage);
                allowNextMessage();
            }
        } catch (error) {
            console.error(error);
            waitingForReply = false;
            const entry = pendingEntry || findPendingByTempId(userMessage.id);
            if (entry) {
                renderedMessages.delete(entry.key);
                if (entry.element && entry.element.parentElement) {
                    entry.element.parentElement.removeChild(entry.element);
                }
                removePendingEntry(entry);
            }
            renderMessage({
                id: generateId(),
                session_id: sessionId,
                player_id: playerId,
                message: 'Nao consegui enviar sua mensagem. Tente novamente em instantes.',
                is_from_user: false,
                created_at: new Date().toISOString(),
            });
        } finally {
            if (!sequencedMode) {
                sequencedMode = true;
            }
            if (waitingForReply) {
                sendButton.removeAttribute('aria-busy');
                sendButton.disabled = true;
                statusIndicator.textContent = 'Aguardando resposta...';
            } else {
                toggleSendingState(false);
            }
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
            console.warn('Historico indisponivel', error);
        }
    };

    const connectStream = () => {
        const streamUrl = `/api/messages/stream?sessao=${encodeURIComponent(sessionId)}&player=${encodeURIComponent(playerId)}`;
        const source = new EventSource(streamUrl);

        source.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data && data.message) {
                    if (data.is_from_user) {
                        const pendingEntry = findPendingMatch(data);
                        if (pendingEntry) {
                            replacePendingMessage(pendingEntry, data);
                            return;
                        }
                    }
                    renderMessage(data);
                    if (!data.is_from_user) {
                        allowNextMessage();
                    }
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
            statusIndicator.textContent = waitingForReply ? 'Aguardando resposta...' : 'Online';
        };
    };

    textarea.addEventListener('input', () => {
        textarea.style.height = 'auto';
        textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
        if (!waitingForReply) {
            sendButton.disabled = textarea.value.trim().length === 0;
        }
    });

    form.addEventListener('submit', (event) => {
        event.preventDefault();
        if (waitingForReply) {
            return;
        }
        const value = textarea.value;
        textarea.value = '';
        textarea.style.height = 'auto';
        sendButton.disabled = true;
        sendMessage(value);
        textarea.focus();
    });

    loadHistory().then(() => {
        connectStream();
        toggleSendingState(false);
    });
})();
