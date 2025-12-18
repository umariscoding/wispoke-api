(function() {
  'use strict';

  // Get configuration from script tag
  const scriptTag = document.currentScript;
  const companySlug = scriptTag?.getAttribute('data-company-slug');
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000';
  const position = scriptTag?.getAttribute('data-position') || 'bottom-right';
  const primaryColor = scriptTag?.getAttribute('data-primary-color') || '#6366f1';

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

  // Generate unique session ID
  const sessionId = 'chatevo_' + Math.random().toString(36).substr(2, 9);

  // CSS Styles
  const styles = `
    .chatevo-widget-container * {
      box-sizing: border-box;
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    }

    .chatevo-toggle-btn {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 20px;
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: ${primaryColor};
      border: none;
      cursor: pointer;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 999998;
    }

    .chatevo-toggle-btn:hover {
      transform: scale(1.05);
      box-shadow: 0 6px 25px rgba(0, 0, 0, 0.2);
    }

    .chatevo-toggle-btn svg {
      width: 28px;
      height: 28px;
      fill: white;
      transition: transform 0.3s ease;
    }

    .chatevo-toggle-btn.open svg {
      transform: rotate(90deg);
    }

    .chatevo-modal-overlay {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.5);
      backdrop-filter: blur(4px);
      z-index: 999999;
      opacity: 0;
      visibility: hidden;
      transition: all 0.3s ease;
    }

    .chatevo-modal-overlay.open {
      opacity: 1;
      visibility: visible;
    }

    .chatevo-modal {
      position: fixed;
      ${position === 'bottom-left' ? 'left: 20px;' : 'right: 20px;'}
      bottom: 90px;
      width: 400px;
      max-width: calc(100vw - 40px);
      height: 600px;
      max-height: calc(100vh - 120px);
      background: #ffffff;
      border-radius: 16px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      display: flex;
      flex-direction: column;
      overflow: hidden;
      z-index: 1000000;
      transform: translateY(20px) scale(0.95);
      opacity: 0;
      visibility: hidden;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .chatevo-modal.open {
      transform: translateY(0) scale(1);
      opacity: 1;
      visibility: visible;
    }

    @media (max-width: 480px) {
      .chatevo-modal {
        left: 10px;
        right: 10px;
        bottom: 10px;
        width: auto;
        max-width: none;
        height: calc(100vh - 20px);
        max-height: none;
        border-radius: 12px;
      }

      .chatevo-toggle-btn {
        bottom: 15px;
        ${position === 'bottom-left' ? 'left: 15px;' : 'right: 15px;'}
      }
    }

    .chatevo-header {
      background: ${primaryColor};
      padding: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-shrink: 0;
    }

    .chatevo-header-info {
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .chatevo-header-avatar {
      width: 44px;
      height: 44px;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .chatevo-header-avatar svg {
      width: 24px;
      height: 24px;
      fill: white;
    }

    .chatevo-header-text h3 {
      margin: 0;
      font-size: 16px;
      font-weight: 600;
      color: white;
    }

    .chatevo-header-text p {
      margin: 4px 0 0;
      font-size: 12px;
      color: rgba(255, 255, 255, 0.8);
    }

    .chatevo-close-btn {
      width: 36px;
      height: 36px;
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.15);
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: background 0.2s ease;
    }

    .chatevo-close-btn:hover {
      background: rgba(255, 255, 255, 0.25);
    }

    .chatevo-close-btn svg {
      width: 20px;
      height: 20px;
      stroke: white;
      stroke-width: 2;
      fill: none;
    }

    .chatevo-messages {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      background: #f9fafb;
    }

    .chatevo-messages::-webkit-scrollbar {
      width: 6px;
    }

    .chatevo-messages::-webkit-scrollbar-track {
      background: transparent;
    }

    .chatevo-messages::-webkit-scrollbar-thumb {
      background: #d1d5db;
      border-radius: 3px;
    }

    .chatevo-message {
      display: flex;
      gap: 10px;
      max-width: 85%;
      animation: chatevo-fadeIn 0.3s ease;
    }

    @keyframes chatevo-fadeIn {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }

    .chatevo-message.user {
      align-self: flex-end;
      flex-direction: row-reverse;
    }

    .chatevo-message-avatar {
      width: 32px;
      height: 32px;
      border-radius: 50%;
      background: ${primaryColor};
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }

    .chatevo-message.user .chatevo-message-avatar {
      background: #6b7280;
    }

    .chatevo-message-avatar svg {
      width: 16px;
      height: 16px;
      fill: white;
    }

    .chatevo-message-content {
      padding: 12px 16px;
      border-radius: 16px;
      background: white;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
      font-size: 14px;
      line-height: 1.5;
      color: #374151;
    }

    .chatevo-message.user .chatevo-message-content {
      background: ${primaryColor};
      color: white;
      border-bottom-right-radius: 4px;
    }

    .chatevo-message:not(.user) .chatevo-message-content {
      border-bottom-left-radius: 4px;
    }

    .chatevo-welcome {
      text-align: center;
      padding: 40px 20px;
      color: #6b7280;
    }

    .chatevo-welcome-icon {
      width: 64px;
      height: 64px;
      background: ${primaryColor}15;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 16px;
    }

    .chatevo-welcome-icon svg {
      width: 32px;
      height: 32px;
      fill: ${primaryColor};
    }

    .chatevo-welcome h4 {
      margin: 0 0 8px;
      font-size: 18px;
      font-weight: 600;
      color: #1f2937;
    }

    .chatevo-welcome p {
      margin: 0;
      font-size: 14px;
    }

    .chatevo-typing {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 12px 16px;
      background: white;
      border-radius: 16px;
      border-bottom-left-radius: 4px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
      width: fit-content;
    }

    .chatevo-typing-dot {
      width: 8px;
      height: 8px;
      background: #9ca3af;
      border-radius: 50%;
      animation: chatevo-bounce 1.4s infinite ease-in-out;
    }

    .chatevo-typing-dot:nth-child(1) { animation-delay: -0.32s; }
    .chatevo-typing-dot:nth-child(2) { animation-delay: -0.16s; }

    @keyframes chatevo-bounce {
      0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
      40% { transform: scale(1); opacity: 1; }
    }

    .chatevo-input-area {
      padding: 16px 20px;
      background: white;
      border-top: 1px solid #e5e7eb;
      display: flex;
      gap: 12px;
      align-items: flex-end;
      flex-shrink: 0;
    }

    .chatevo-input-wrapper {
      flex: 1;
      position: relative;
    }

    .chatevo-input {
      width: 100%;
      padding: 12px 16px;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      font-size: 14px;
      resize: none;
      max-height: 120px;
      line-height: 1.5;
      transition: border-color 0.2s ease, box-shadow 0.2s ease;
      outline: none;
    }

    .chatevo-input:focus {
      border-color: ${primaryColor};
      box-shadow: 0 0 0 3px ${primaryColor}20;
    }

    .chatevo-input::placeholder {
      color: #9ca3af;
    }

    .chatevo-send-btn {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      background: ${primaryColor};
      border: none;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 0.2s ease;
      flex-shrink: 0;
    }

    .chatevo-send-btn:hover:not(:disabled) {
      background: ${primaryColor}dd;
      transform: scale(1.05);
    }

    .chatevo-send-btn:disabled {
      background: #d1d5db;
      cursor: not-allowed;
    }

    .chatevo-send-btn svg {
      width: 20px;
      height: 20px;
      fill: white;
    }

    .chatevo-powered {
      text-align: center;
      padding: 8px;
      font-size: 11px;
      color: #9ca3af;
      background: #f9fafb;
      border-top: 1px solid #e5e7eb;
    }

    .chatevo-powered a {
      color: ${primaryColor};
      text-decoration: none;
      font-weight: 500;
    }

    .chatevo-powered a:hover {
      text-decoration: underline;
    }
  `;

  // Inject styles
  const styleSheet = document.createElement('style');
  styleSheet.textContent = styles;
  document.head.appendChild(styleSheet);

  // SVG Icons
  const icons = {
    chat: `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h10v2H7zm0-3h10v2H7zm0 6h7v2H7z"/></svg>`,
    close: `<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
    send: `<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>`,
    bot: `<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 011 1v3a1 1 0 01-1 1h-1v1a2 2 0 01-2 2H5a2 2 0 01-2-2v-1H2a1 1 0 01-1-1v-3a1 1 0 011-1h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2M7.5 13A2.5 2.5 0 005 15.5 2.5 2.5 0 007.5 18a2.5 2.5 0 002.5-2.5A2.5 2.5 0 007.5 13m9 0a2.5 2.5 0 00-2.5 2.5 2.5 2.5 0 002.5 2.5 2.5 2.5 0 002.5-2.5 2.5 2.5 0 00-2.5-2.5z"/></svg>`,
    user: `<svg viewBox="0 0 24 24"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>`,
    message: `<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zM6 9h12v2H6V9zm8 5H6v-2h8v2zm4-6H6V6h12v2z"/></svg>`
  };

  // Create widget container
  const container = document.createElement('div');
  container.className = 'chatevo-widget-container';
  container.innerHTML = `
    <button class="chatevo-toggle-btn" aria-label="Open chat">
      ${icons.chat}
    </button>
    <div class="chatevo-modal-overlay"></div>
    <div class="chatevo-modal">
      <div class="chatevo-header">
        <div class="chatevo-header-info">
          <div class="chatevo-header-avatar">${icons.bot}</div>
          <div class="chatevo-header-text">
            <h3>Chat Assistant</h3>
            <p>We typically reply instantly</p>
          </div>
        </div>
        <button class="chatevo-close-btn" aria-label="Close chat">
          ${icons.close}
        </button>
      </div>
      <div class="chatevo-messages">
        <div class="chatevo-welcome">
          <div class="chatevo-welcome-icon">${icons.message}</div>
          <h4>Welcome!</h4>
          <p>How can we help you today?</p>
        </div>
      </div>
      <div class="chatevo-input-area">
        <div class="chatevo-input-wrapper">
          <textarea class="chatevo-input" placeholder="Type your message..." rows="1"></textarea>
        </div>
        <button class="chatevo-send-btn" aria-label="Send message" disabled>
          ${icons.send}
        </button>
      </div>
      <div class="chatevo-powered">
        Powered by <a href="https://chatevo.com" target="_blank" rel="noopener">ChatEvo</a>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  // Get DOM elements
  const toggleBtn = container.querySelector('.chatevo-toggle-btn');
  const modal = container.querySelector('.chatevo-modal');
  const overlay = container.querySelector('.chatevo-modal-overlay');
  const closeBtn = container.querySelector('.chatevo-close-btn');
  const messagesContainer = container.querySelector('.chatevo-messages');
  const input = container.querySelector('.chatevo-input');
  const sendBtn = container.querySelector('.chatevo-send-btn');
  const headerTitle = container.querySelector('.chatevo-header-text h3');
  const headerSubtitle = container.querySelector('.chatevo-header-text p');

  // Fetch company info
  async function fetchCompanyInfo() {
    try {
      const response = await fetch(`${apiUrl}/public/chatbot/${companySlug}`);
      if (response.ok) {
        companyInfo = await response.json();
        if (companyInfo.chatbot_title) {
          headerTitle.textContent = companyInfo.chatbot_title;
        }
        if (companyInfo.chatbot_description) {
          headerSubtitle.textContent = companyInfo.chatbot_description;
        }
      }
    } catch (error) {
      console.error('ChatEvo Widget: Failed to fetch company info', error);
    }
  }

  // Toggle chat modal
  function toggleChat() {
    isOpen = !isOpen;
    modal.classList.toggle('open', isOpen);
    overlay.classList.toggle('open', isOpen);
    toggleBtn.classList.toggle('open', isOpen);

    if (isOpen) {
      input.focus();
      if (!companyInfo) {
        fetchCompanyInfo();
      }
    }
  }

  // Close chat
  function closeChat() {
    isOpen = false;
    modal.classList.remove('open');
    overlay.classList.remove('open');
    toggleBtn.classList.remove('open');
  }

  // Add message to UI
  function addMessage(content, isUser = false) {
    // Remove welcome message if exists
    const welcome = messagesContainer.querySelector('.chatevo-welcome');
    if (welcome) welcome.remove();

    const messageDiv = document.createElement('div');
    messageDiv.className = `chatevo-message ${isUser ? 'user' : ''}`;
    messageDiv.innerHTML = `
      <div class="chatevo-message-avatar">
        ${isUser ? icons.user : icons.bot}
      </div>
      <div class="chatevo-message-content">${escapeHtml(content)}</div>
    `;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
    return messageDiv;
  }

  // Show typing indicator
  function showTyping() {
    const typingDiv = document.createElement('div');
    typingDiv.className = 'chatevo-message';
    typingDiv.id = 'chatevo-typing';
    typingDiv.innerHTML = `
      <div class="chatevo-message-avatar">${icons.bot}</div>
      <div class="chatevo-typing">
        <div class="chatevo-typing-dot"></div>
        <div class="chatevo-typing-dot"></div>
        <div class="chatevo-typing-dot"></div>
      </div>
    `;
    messagesContainer.appendChild(typingDiv);
    scrollToBottom();
  }

  // Hide typing indicator
  function hideTyping() {
    const typing = document.getElementById('chatevo-typing');
    if (typing) typing.remove();
  }

  // Scroll to bottom of messages
  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Escape HTML to prevent XSS
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Send message
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
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message,
          chat_id: chatId
        })
      });

      if (!response.ok) {
        throw new Error('Failed to send message');
      }

      hideTyping();

      // Handle streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let aiMessageDiv = null;
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
                const content = data.content
                  .replace(/\\n/g, '\n')
                  .replace(/\\r/g, '\r')
                  .replace(/\\"/g, '"');
                fullResponse += content;

                if (!aiMessageDiv) {
                  aiMessageDiv = addMessage('');
                }
                aiMessageDiv.querySelector('.chatevo-message-content').textContent = fullResponse;
                scrollToBottom();
              } else if (data.type === 'error') {
                throw new Error(data.error);
              }
            } catch (e) {
              // Skip invalid JSON
            }
          }
        }
      }

      messages.push({ role: 'user', content: message });
      messages.push({ role: 'assistant', content: fullResponse });

    } catch (error) {
      hideTyping();
      addMessage('Sorry, something went wrong. Please try again.');
      console.error('ChatEvo Widget: Error sending message', error);
    } finally {
      isLoading = false;
      updateSendButton();
    }
  }

  // Update send button state
  function updateSendButton() {
    sendBtn.disabled = !input.value.trim() || isLoading;
  }

  // Auto-resize textarea
  function autoResize() {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  }

  // Event listeners
  toggleBtn.addEventListener('click', toggleChat);
  closeBtn.addEventListener('click', closeChat);
  overlay.addEventListener('click', closeChat);

  sendBtn.addEventListener('click', sendMessage);

  input.addEventListener('input', () => {
    updateSendButton();
    autoResize();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  // Close on escape key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && isOpen) {
      closeChat();
    }
  });

  // Prefetch company info
  fetchCompanyInfo();

})();
