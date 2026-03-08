(function() {
  'use strict';

  // Get configuration from script tag
  const scriptTag = document.currentScript;
  const companySlug = scriptTag?.getAttribute('data-company-slug');
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000';
  const position = scriptTag?.getAttribute('data-position') || 'bottom-right';
  const primaryColor = scriptTag?.getAttribute('data-primary-color') || '#6366f1';
  const theme = scriptTag?.getAttribute('data-theme') || 'dark';

  // Get custom texts - properly check for attribute existence
  const welcomeTextAttr = scriptTag?.getAttribute('data-welcome-text');
  const subtitleTextAttr = scriptTag?.getAttribute('data-subtitle-text');
  const welcomeText = (welcomeTextAttr !== null && welcomeTextAttr !== '') ? welcomeTextAttr : 'Hi there! How can we help you today?';
  const subtitleText = (subtitleTextAttr !== null && subtitleTextAttr !== '') ? subtitleTextAttr : 'We typically reply instantly';

  if (!companySlug) {
    console.error('ChatEvo Widget: Missing data-company-slug attribute');
    return;
  }

  // Widget State
  let isOpen = false;
  let chatId = null;
  let messages = [];
  let isLoading = false;
  let companyInfo = null;

  // Theme colors
  const darkColors = {
    bg: '#09090b',
    bgInput: '#27272a',
    text: '#e4e4e7',
    textSecondary: '#a1a1aa',
    textMuted: '#71717a',
    border: '#27272a',
    scrollbar: '#3f3f46',
    focusRing: '#3f3f46',
  };

  const lightColors = {
    bg: '#ffffff',
    bgInput: '#f4f4f5',
    text: '#18181b',
    textSecondary: '#3f3f46',
    textMuted: '#71717a',
    border: '#e4e4e7',
    scrollbar: '#d4d4d8',
    focusRing: '#d4d4d8',
  };

  const colors = theme === 'light' ? lightColors : darkColors;

  // CSS Styles with theme support
  const styles = `
    .chatevo-widget-container * {
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      margin: 0;
      padding: 0;
    }

    .chatevo-toggle-btn {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 20px;
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: ${primaryColor};
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0, 0, 0, ${theme === 'light' ? '0.15' : '0.4'});
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      z-index: 999998;
    }

    .chatevo-toggle-btn:hover {
      transform: scale(1.05);
    }

    .chatevo-toggle-btn svg {
      width: 24px;
      height: 24px;
      color: white;
      transition: all 0.2s ease;
    }

    .chatevo-toggle-btn.open svg.chat-icon {
      opacity: 0;
      transform: scale(0);
    }

    .chatevo-toggle-btn svg.close-icon {
      position: absolute;
      opacity: 0;
      transform: scale(0);
    }

    .chatevo-toggle-btn.open svg.close-icon {
      opacity: 1;
      transform: scale(1);
    }

    .chatevo-modal {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 88px;
      width: 420px;
      max-width: calc(100vw - 40px);
      height: 600px;
      max-height: calc(100vh - 120px);
      background: ${colors.bg};
      border-radius: 16px;
      border: 1px solid ${colors.border};
      box-shadow: 0 20px 50px rgba(0, 0, 0, ${theme === 'light' ? '0.15' : '0.5'});
      display: flex;
      flex-direction: column;
      overflow: hidden;
      z-index: 999999;
      transform: translateY(10px);
      opacity: 0;
      visibility: hidden;
      transition: all 0.2s ease;
    }

    .chatevo-modal.open {
      transform: translateY(0);
      opacity: 1;
      visibility: visible;
    }

    @media (max-width: 480px) {
      .chatevo-modal {
        left: 8px;
        right: 8px;
        bottom: 8px;
        top: 8px;
        width: auto;
        max-width: none;
        height: auto;
        max-height: none;
      }
    }

    .chatevo-header {
      padding: 16px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }

    .chatevo-header-text h3 {
      font-size: 16px;
      font-weight: 500;
      color: ${colors.text};
    }

    .chatevo-header-text p {
      font-size: 12px;
      color: ${colors.textMuted};
      margin-top: 2px;
    }

    .chatevo-close-btn {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      background: transparent;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: ${colors.textMuted};
      transition: all 0.15s;
    }

    .chatevo-close-btn:hover {
      background: ${colors.bgInput};
      color: ${colors.text};
    }

    .chatevo-close-btn svg {
      width: 18px;
      height: 18px;
    }

    .chatevo-messages {
      flex: 1;
      overflow-y: auto;
      padding: 8px 16px;
      display: flex;
      flex-direction: column;
    }

    .chatevo-messages::-webkit-scrollbar {
      width: 4px;
    }

    .chatevo-messages::-webkit-scrollbar-thumb {
      background: ${colors.scrollbar};
      border-radius: 4px;
    }

    .chatevo-message {
      max-width: 85%;
      margin-bottom: 8px;
      animation: chatevo-fadeIn 0.2s ease;
    }

    @keyframes chatevo-fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    .chatevo-message.user {
      align-self: flex-end;
    }

    .chatevo-message.user .chatevo-message-content {
      background: ${colors.bgInput};
      color: ${colors.text};
      border-radius: 18px;
      padding: 10px 14px;
    }

    .chatevo-message:not(.user) .chatevo-message-content {
      color: ${colors.textSecondary};
      padding: 4px 0;
      line-height: 1.6;
    }

    .chatevo-message-content {
      font-size: 14px;
      white-space: pre-wrap;
      word-break: break-word;
    }

    .chatevo-welcome {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      text-align: center;
      padding: 20px;
    }

    .chatevo-welcome h4 {
      font-size: 15px;
      font-weight: 400;
      color: ${colors.textSecondary};
      margin-bottom: 4px;
    }

    .chatevo-welcome p {
      font-size: 13px;
      color: ${colors.textMuted};
    }

    .chatevo-typing {
      display: flex;
      gap: 4px;
      padding: 8px 0;
    }

    .chatevo-typing-dot {
      width: 6px;
      height: 6px;
      background: ${colors.textMuted};
      border-radius: 50%;
      animation: chatevo-bounce 1.4s infinite ease-in-out;
    }

    .chatevo-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .chatevo-typing-dot:nth-child(2) { animation-delay: -0.16s; }

    @keyframes chatevo-bounce {
      0%, 80%, 100% { opacity: 0.4; }
      40% { opacity: 1; }
    }

    .chatevo-input-area {
      padding: 16px;
      flex-shrink: 0;
    }

    .chatevo-input-wrapper {
      display: flex;
      align-items: flex-end;
      background: ${colors.bgInput};
      border-radius: 24px;
      padding: 8px 8px 8px 16px;
      transition: all 0.15s;
    }

    .chatevo-input-wrapper:focus-within {
      box-shadow: 0 0 0 2px ${colors.focusRing};
    }

    .chatevo-input {
      flex: 1;
      border: none;
      background: transparent;
      color: ${colors.text};
      font-size: 14px;
      resize: none;
      outline: none;
      max-height: 100px;
      min-height: 24px;
      line-height: 1.4;
      padding: 4px 0;
    }

    .chatevo-input::placeholder {
      color: ${colors.textMuted};
    }

    .chatevo-send-btn {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: transparent;
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      color: ${colors.textMuted};
      transition: all 0.15s;
      flex-shrink: 0;
    }

    .chatevo-send-btn:hover:not(:disabled) {
      color: ${colors.text};
    }

    .chatevo-send-btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
    }

    .chatevo-send-btn svg {
      width: 18px;
      height: 18px;
    }

    .chatevo-powered {
      text-align: center;
      padding: 8px;
      font-size: 10px;
      color: ${colors.textMuted};
      border-top: 1px solid ${colors.border};
    }

    .chatevo-powered a {
      color: ${colors.textMuted};
      text-decoration: none;
    }

    .chatevo-powered a:hover {
      color: ${colors.textSecondary};
    }

    .chatevo-cursor {
      display: inline-block;
      width: 2px;
      height: 14px;
      background: ${colors.textMuted};
      margin-left: 2px;
      animation: chatevo-blink 0.8s infinite;
      vertical-align: text-bottom;
    }

    @keyframes chatevo-blink {
      0%, 50% { opacity: 1; }
      51%, 100% { opacity: 0; }
    }
  `;

  // Inject styles
  const styleSheet = document.createElement('style');
  styleSheet.textContent = styles;
  document.head.appendChild(styleSheet);

  // SVG Icons
  const chatIcon = `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`;
  const closeIcon = `<svg class="close-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
  const sendIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`;

  // Create widget
  const container = document.createElement('div');
  container.className = 'chatevo-widget-container';
  container.innerHTML = `
    <button class="chatevo-toggle-btn" aria-label="Open chat">
      ${chatIcon}
      ${closeIcon}
    </button>
    <div class="chatevo-modal">
      <div class="chatevo-header">
        <div class="chatevo-header-text">
          <h3 class="chatevo-title">Chat Assistant</h3>
          <p class="chatevo-subtitle">${subtitleText}</p>
        </div>
        <button class="chatevo-close-btn" aria-label="Close">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="chatevo-messages">
        <div class="chatevo-welcome">
          <h4 class="chatevo-welcome-text">${welcomeText}</h4>
          <p>Ask us anything</p>
        </div>
      </div>
      <div class="chatevo-input-area">
        <div class="chatevo-input-wrapper">
          <textarea class="chatevo-input" placeholder="Type your message..." rows="1"></textarea>
          <button class="chatevo-send-btn" disabled>
            ${sendIcon}
          </button>
        </div>
      </div>
      <div class="chatevo-powered">
        Powered by <a href="https://chatevo.com" target="_blank">ChatEvo</a>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  // DOM elements
  const toggleBtn = container.querySelector('.chatevo-toggle-btn');
  const modal = container.querySelector('.chatevo-modal');
  const closeBtn = container.querySelector('.chatevo-close-btn');
  const messagesContainer = container.querySelector('.chatevo-messages');
  const input = container.querySelector('.chatevo-input');
  const sendBtn = container.querySelector('.chatevo-send-btn');
  const headerTitle = container.querySelector('.chatevo-title');

  // Fetch company info
  async function fetchCompanyInfo() {
    try {
      const response = await fetch(`${apiUrl}/public/chatbot/${companySlug}`);
      if (response.ok) {
        companyInfo = await response.json();
        if (companyInfo.chatbot_title) {
          headerTitle.textContent = companyInfo.chatbot_title;
        }
      }
    } catch (e) {
      console.error('ChatEvo Widget: Failed to fetch company info');
    }
  }

  function toggleChat() {
    isOpen = !isOpen;
    modal.classList.toggle('open', isOpen);
    toggleBtn.classList.toggle('open', isOpen);
    if (isOpen) {
      setTimeout(() => input.focus(), 100);
      if (!companyInfo) fetchCompanyInfo();
    }
  }

  function closeChat() {
    isOpen = false;
    modal.classList.remove('open');
    toggleBtn.classList.remove('open');
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function addMessage(content, isUser = false) {
    const welcome = messagesContainer.querySelector('.chatevo-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = `chatevo-message ${isUser ? 'user' : ''}`;
    div.innerHTML = `<div class="chatevo-message-content">${escapeHtml(content)}</div>`;
    messagesContainer.appendChild(div);
    scrollToBottom();
    return div;
  }

  function showTyping() {
    const div = document.createElement('div');
    div.className = 'chatevo-message';
    div.id = 'chatevo-typing';
    div.innerHTML = `<div class="chatevo-typing"><div class="chatevo-typing-dot"></div><div class="chatevo-typing-dot"></div><div class="chatevo-typing-dot"></div></div>`;
    messagesContainer.appendChild(div);
    scrollToBottom();
  }

  function hideTyping() {
    const el = document.getElementById('chatevo-typing');
    if (el) el.remove();
  }

  async function sendMessage() {
    const message = input.value.trim();
    if (!message || isLoading) return;

    isLoading = true;
    input.value = '';
    input.style.height = 'auto';
    sendBtn.disabled = true;

    addMessage(message, true);
    showTyping();

    try {
      const response = await fetch(`${apiUrl}/public/chatbot/${companySlug}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, chat_id: chatId })
      });

      if (!response.ok) throw new Error('Failed');

      hideTyping();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiDiv = null;
      let fullResponse = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.type === 'start') {
                chatId = data.chat_id;
              } else if (data.type === 'chunk' && data.content) {
                fullResponse += data.content.replace(/\\n/g, '\n').replace(/\\r/g, '\r').replace(/\\"/g, '"');
                if (!aiDiv) aiDiv = addMessage('');
                aiDiv.querySelector('.chatevo-message-content').innerHTML = escapeHtml(fullResponse) + '<span class="chatevo-cursor"></span>';
                scrollToBottom();
              } else if (data.type === 'end' && aiDiv) {
                const cursor = aiDiv.querySelector('.chatevo-cursor');
                if (cursor) cursor.remove();
              } else if (data.type === 'error') {
                throw new Error(data.error);
              }
            } catch (e) {}
          }
        }
      }

      messages.push({ role: 'user', content: message });
      messages.push({ role: 'assistant', content: fullResponse });

    } catch (e) {
      hideTyping();
      addMessage('Sorry, something went wrong. Please try again.');
    } finally {
      isLoading = false;
      updateSendButton();
    }
  }

  function updateSendButton() {
    sendBtn.disabled = !input.value.trim() || isLoading;
  }

  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 100) + 'px';
  }

  // Events
  toggleBtn.addEventListener('click', toggleChat);
  closeBtn.addEventListener('click', closeChat);
  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('input', () => { updateSendButton(); autoResize(); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen) closeChat(); });

  fetchCompanyInfo();
})();
