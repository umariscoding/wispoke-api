(function() {
  'use strict';

  // Get minimum config from script tag
  const scriptTag = document.currentScript;
  const companySlug = scriptTag?.getAttribute('data-company-slug');
  const apiUrl = scriptTag?.getAttribute('data-api-url') || 'http://localhost:8000';

  if (!companySlug) {
    console.error('ChatEvo Widget: Missing data-company-slug attribute');
    return;
  }

  // Fallback values from data attributes
  const fallbackConfig = {
    position: scriptTag?.getAttribute('data-position') || 'bottom-right',
    primaryColor: scriptTag?.getAttribute('data-primary-color') || '#6366f1',
    theme: scriptTag?.getAttribute('data-theme') || 'dark',
    welcomeText: scriptTag?.getAttribute('data-welcome-text') || 'Hi there! How can we help you today?',
    subtitleText: scriptTag?.getAttribute('data-subtitle-text') || 'We typically reply instantly',
    headerColor: '',
    placeholderText: 'Type your message...',
    showHeaderSubtitle: true,
    hideBranding: false,
    autoOpenDelay: 0,
    buttonIcon: 'chat',
    chatTemplate: 'default',
    suggestedMessages: [],
  };

  // Fetch settings from backend, then initialize widget
  async function loadAndInit() {
    let config = { ...fallbackConfig };

    try {
      const res = await fetch(`${apiUrl}/public/chatbot/${companySlug}/embed-settings`);
      if (res.ok) {
        const data = await res.json();
        const s = data.settings;
        if (s) {
          config.theme = s.theme || config.theme;
          config.position = (s.position === 'left' ? 'bottom-left' : 'bottom-right');
          config.primaryColor = s.primaryColor || config.primaryColor;
          config.welcomeText = s.welcomeText ?? config.welcomeText;
          config.subtitleText = s.subtitleText ?? config.subtitleText;
          config.placeholderText = s.placeholderText || config.placeholderText;
          config.showHeaderSubtitle = s.showHeaderSubtitle ?? config.showHeaderSubtitle;
          config.hideBranding = s.hideBranding ?? config.hideBranding;
          config.autoOpenDelay = s.autoOpenDelay ?? config.autoOpenDelay;
          config.buttonIcon = s.buttonIcon || config.buttonIcon;
          config.headerColor = s.headerColor ?? config.headerColor;
          config.chatTemplate = s.chatTemplate || config.chatTemplate;
          config.suggestedMessages = Array.isArray(s.suggestedMessages) ? s.suggestedMessages.filter(Boolean) : config.suggestedMessages;
        }
      }
    } catch (e) {
      // Use fallback config
    }

    initWidget(config);
  }

  function initWidget(config) {
    const {
      position, primaryColor, headerColor, theme, welcomeText, subtitleText,
      placeholderText, showHeaderSubtitle, hideBranding, autoOpenDelay,
      buttonIcon, chatTemplate, suggestedMessages
    } = config;

    const resolvedHeaderColor = headerColor || primaryColor;

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

    // Button icon SVGs
    const buttonIcons = {
      chat: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 21 1.9-5.7a8.5 8.5 0 1 1 3.8 3.8z"></path></svg>`,
      message: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="20" height="16" x="2" y="4" rx="2"></rect><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"></path></svg>`,
      headset: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14h3a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a9 9 0 0 1 18 0v7a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3"></path></svg>`,
      sparkle: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"></path><path d="M5 3v4"></path><path d="M19 17v4"></path><path d="M3 5h4"></path><path d="M17 19h4"></path></svg>`,
      bolt: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>`,
      help: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path><path d="M12 17h.01"></path></svg>`,
      robot: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"></path><rect width="16" height="12" x="4" y="8" rx="2"></rect><path d="M2 14h2"></path><path d="M20 14h2"></path><path d="M15 13v2"></path><path d="M9 13v2"></path></svg>`,
      wand: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72Z"></path><path d="m14 7 3 3"></path><path d="M5 6v4"></path><path d="M19 14v4"></path><path d="M10 2v2"></path><path d="M7 8H3"></path><path d="M21 16h-4"></path><path d="M11 3H9"></path></svg>`,
      phone: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z"></path></svg>`,
      bubble: `<svg class="chat-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 9a2 2 0 0 1-2 2H6l-4 4V4c0-1.1.9-2 2-2h8a2 2 0 0 1 2 2v5Z"></path><path d="M18 9h2a2 2 0 0 1 2 2v11l-4-4h-6a2 2 0 0 1-2-2v-1"></path></svg>`,
    };

    const selectedIcon = buttonIcons[buttonIcon] || buttonIcons.chat;
    const closeIcon = `<svg class="close-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
    const sendIcon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>`;

    // Template-specific values
    const isBubbles = chatTemplate === 'bubbles';
    const isMinimal = chatTemplate === 'minimal';

    const modalRadius = isBubbles ? '24px' : isMinimal ? '8px' : '16px';
    // Header radius removed — modal overflow:hidden clips the corners
    const toggleRadius = isMinimal ? '12px' : '50%';
    const inputRadius = isBubbles ? '28px' : isMinimal ? '8px' : '24px';
    const modalShadow = isMinimal
      ? `0 8px 30px rgba(0, 0, 0, ${theme === 'light' ? '0.1' : '0.4'})`
      : `0 20px 50px rgba(0, 0, 0, ${theme === 'light' ? '0.15' : '0.5'})`;

    // Header styling per template
    const headerBg = isMinimal ? colors.bg : resolvedHeaderColor;
    const headerBorder = isMinimal ? `border-bottom: 1px solid ${colors.border};` : '';
    const headerTitleColor = isMinimal ? colors.text : '#ffffff';
    const headerSubtitleColor = isMinimal ? colors.textMuted : 'rgba(255, 255, 255, 0.7)';
    const headerPadding = isBubbles ? '20px 16px' : isMinimal ? '14px 16px' : '16px';
    const headerTitleSize = isMinimal ? '14px' : '16px';
    const headerTitleWeight = isMinimal ? '600' : isBubbles ? '600' : '500';
    const headerSubtitleSize = isMinimal ? '11px' : '12px';

    // Close button per template
    const closeBtnRadius = isBubbles ? '16px' : isMinimal ? '6px' : '8px';
    const closeBtnColor = isMinimal ? colors.textMuted : 'rgba(255, 255, 255, 0.7)';
    const closeBtnHoverBg = isMinimal ? (theme === 'light' ? '#f4f4f5' : '#27272a') : 'rgba(255, 255, 255, 0.15)';
    const closeBtnHoverColor = isMinimal ? colors.text : '#ffffff';
    const closeBtnSize = isMinimal ? '28px' : '32px';
    const closeBtnIconSize = isMinimal ? '16px' : '18px';

    // Bubbles template: close button has bg
    const closeBtnBg = isBubbles ? 'rgba(255,255,255,0.15)' : 'transparent';

    // Send button per template
    const sendBtnBg = isBubbles ? primaryColor : isMinimal ? primaryColor : 'transparent';
    const sendBtnDisabledBg = isBubbles ? colors.bgInput : isMinimal ? 'transparent' : 'transparent';
    const sendBtnColor = isBubbles ? '#ffffff' : isMinimal ? '#ffffff' : colors.textMuted;
    const sendBtnDisabledColor = isBubbles ? colors.textMuted : isMinimal ? colors.textMuted : colors.textMuted;
    const sendBtnSize = isBubbles ? '34px' : isMinimal ? '30px' : '32px';
    const sendBtnRadius = isMinimal ? '6px' : '50%';
    const sendBtnIconSize = isBubbles ? '16px' : isMinimal ? '14px' : '18px';

    // Input area styling
    const inputWrapperBg = isMinimal ? 'transparent' : colors.bgInput;
    const inputWrapperBorder = isMinimal ? `border: 1px solid ${colors.border};` : '';
    const inputPadding = isBubbles ? '8px 8px 8px 18px' : isMinimal ? '8px 8px 8px 12px' : '8px 8px 8px 16px';
    const inputAreaPad = isMinimal ? '12px 14px' : '16px';
    const inputFontSize = isMinimal ? '13px' : '14px';
    const msgAreaPad = isMinimal ? '12px 14px' : '8px 16px';

    // Message styles per template
    let userMsgStyles = '';
    let botMsgContentStyles = '';
    if (isBubbles) {
      userMsgStyles = `
        background: ${primaryColor};
        color: #ffffff;
        border-radius: 20px 20px 4px 20px;
        padding: 10px 16px;
        line-height: 1.5;
      `;
      botMsgContentStyles = `
        background: ${colors.bgInput};
        color: ${colors.text};
        border-radius: 20px 20px 20px 4px;
        padding: 10px 16px;
        line-height: 1.5;
      `;
    } else if (isMinimal) {
      userMsgStyles = `
        background: ${theme === 'light' ? '#f0f0f0' : '#1a1a1e'};
        color: ${colors.text};
        border-radius: 6px;
        padding: 8px 12px;
        font-size: 13px;
        line-height: 1.5;
      `;
      botMsgContentStyles = `
        color: ${colors.textSecondary};
        padding: 6px 0;
        font-size: 13px;
        line-height: 1.6;
      `;
    } else {
      userMsgStyles = `
        background: ${colors.bgInput};
        color: ${colors.text};
        border-radius: 18px;
        padding: 10px 14px;
      `;
      botMsgContentStyles = `
        color: ${colors.textSecondary};
        padding: 4px 0;
        line-height: 1.6;
      `;
    }

    const msgSpacing = isBubbles ? '10px' : isMinimal ? '6px' : '8px';

    // CSS Styles with theme + template support
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
        border-radius: ${toggleRadius};
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
        transition: opacity 0.3s ease, transform 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      }

      .chatevo-toggle-btn svg.chat-icon {
        transform: scale(1) rotate(0deg);
      }

      .chatevo-toggle-btn.open svg.chat-icon {
        opacity: 0;
        transform: scale(0) rotate(90deg);
      }

      .chatevo-toggle-btn svg.close-icon {
        position: absolute;
        opacity: 0;
        transform: scale(0) rotate(-90deg);
      }

      .chatevo-toggle-btn.open svg.close-icon {
        opacity: 1;
        transform: scale(1) rotate(0deg);
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
        border-radius: ${modalRadius};
        ${isMinimal ? `border: 1px solid ${colors.border};` : ''}
        box-shadow: ${modalShadow};
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
        padding: ${headerPadding};
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-shrink: 0;
        background: ${headerBg};
        ${headerBorder}
      }

      .chatevo-header-text {
        display: flex;
        align-items: center;
        gap: ${isBubbles ? '12px' : '0'};
      }

      .chatevo-header-text h3 {
        font-size: ${headerTitleSize};
        font-weight: ${headerTitleWeight};
        color: ${headerTitleColor};
      }

      .chatevo-header-text p {
        font-size: ${headerSubtitleSize};
        color: ${headerSubtitleColor};
        margin-top: ${isMinimal ? '1px' : '2px'};
      }

      .chatevo-close-btn {
        width: ${closeBtnSize};
        height: ${closeBtnSize};
        border-radius: ${closeBtnRadius};
        background: ${closeBtnBg};
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        color: ${closeBtnColor};
        transition: all 0.15s;
      }

      .chatevo-close-btn:hover {
        background: ${closeBtnHoverBg};
        color: ${closeBtnHoverColor};
      }

      .chatevo-close-btn svg {
        width: ${closeBtnIconSize};
        height: ${closeBtnIconSize};
      }

      .chatevo-messages {
        flex: 1;
        overflow-y: auto;
        padding: ${msgAreaPad};
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
        margin-bottom: ${msgSpacing};
        animation: chatevo-fadeIn 0.2s ease;
      }

      @keyframes chatevo-fadeIn {
        from { opacity: 0; transform: translateY(4px); }
        to { opacity: 1; transform: translateY(0); }
      }

      .chatevo-message.user {
        align-self: flex-end;
      }

      .chatevo-message.bot-msg {
        display: flex;
        align-items: ${isBubbles ? 'flex-end' : 'flex-start'};
        gap: 8px;
      }

      .chatevo-message.user .chatevo-message-content {
        ${userMsgStyles}
      }

      .chatevo-message:not(.user) .chatevo-message-content {
        ${botMsgContentStyles}
      }

      .chatevo-message-content {
        font-size: 14px;
        word-break: break-word;
        line-height: 1.6;
      }

      .chatevo-message-content strong {
        font-weight: 600;
        color: ${colors.text};
      }

      .chatevo-message-content em {
        font-style: italic;
      }

      .chatevo-message-content .ce-list {
        margin: 4px 0;
        padding: 0 0 0 20px;
      }

      .chatevo-message-content .ce-list li {
        margin-bottom: 2px;
        line-height: 1.5;
      }

      .chatevo-message-content .ce-code-block {
        background: ${colors.bgInput};
        padding: 10px 12px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 6px 0;
        font-size: 13px;
        line-height: 1.5;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        white-space: pre-wrap;
        word-break: break-word;
      }

      .chatevo-message-content .ce-inline-code {
        background: ${colors.bgInput};
        padding: 1px 5px;
        border-radius: 4px;
        font-size: 13px;
        font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      }

      .chatevo-message.user .chatevo-message-content {
        white-space: pre-wrap;
      }

      .chatevo-welcome {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        text-align: left;
        padding: ${isBubbles ? '24px' : '20px'};
      }

      .chatevo-welcome-centered {
        flex: 1;
        align-items: center;
        justify-content: center;
        text-align: center;
      }

      .chatevo-welcome h4 {
        font-size: ${isBubbles ? '16px' : isMinimal ? '14px' : '15px'};
        font-weight: ${isBubbles ? '500' : '400'};
        color: ${isBubbles ? colors.text : colors.textSecondary};
        margin-bottom: 4px;
      }

      .chatevo-welcome-sub {
        font-size: ${isMinimal ? '12px' : '13px'};
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

      .chatevo-suggested {
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
        padding-top: 12px;
      }

      .chatevo-suggested-btn {
        padding: 8px 14px;
        font-size: 13px;
        border-radius: 10px;
        border: 1.5px solid ${theme === 'light' ? '#d4d4d8' : '#3f3f46'};
        background: transparent;
        color: ${colors.text};
        cursor: pointer;
        text-align: left;
        transition: all 0.15s;
        font-family: inherit;
        line-height: 1.4;
      }

      .chatevo-suggested-btn:hover {
        border-color: ${primaryColor};
        color: ${primaryColor};
        background: ${theme === 'light' ? 'rgba(0,0,0,0.02)' : 'rgba(255,255,255,0.03)'};
      }

      .chatevo-input-area {
        padding: ${inputAreaPad};
        flex-shrink: 0;
      }

      .chatevo-input-wrapper {
        display: flex;
        align-items: center;
        background: ${inputWrapperBg};
        border-radius: ${inputRadius};
        padding: ${inputPadding};
        transition: all 0.15s;
        ${inputWrapperBorder}
      }

      .chatevo-input-wrapper:focus-within {
        ${isMinimal ? `border-color: ${primaryColor}; box-shadow: 0 0 0 1px ${primaryColor}40;` : `box-shadow: 0 0 0 2px ${colors.focusRing};`}
      }

      .chatevo-input {
        flex: 1;
        border: none;
        background: transparent;
        color: ${colors.text};
        font-size: ${inputFontSize};
        resize: none;
        outline: none;
        max-height: 100px;
        min-height: 20px;
        line-height: 20px;
        padding: 0;
      }

      .chatevo-input::placeholder {
        color: ${colors.textMuted};
      }

      .chatevo-send-btn {
        width: ${sendBtnSize};
        height: ${sendBtnSize};
        border-radius: ${sendBtnRadius};
        background: ${sendBtnBg};
        border: none;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        color: ${sendBtnColor};
        transition: all 0.15s;
        flex-shrink: 0;
      }

      .chatevo-send-btn:hover:not(:disabled) {
        ${isBubbles ? `opacity: 0.9;` : isMinimal ? `opacity: 0.9;` : `color: ${colors.text};`}
      }

      .chatevo-send-btn:disabled {
        ${isBubbles ? `background: ${sendBtnDisabledBg}; color: ${sendBtnDisabledColor}; cursor: not-allowed;`
        : isMinimal ? `background: ${sendBtnDisabledBg}; color: ${sendBtnDisabledColor}; opacity: 0.4; cursor: not-allowed;`
        : `opacity: 0.3; cursor: not-allowed;`}
      }

      .chatevo-send-btn svg {
        width: ${sendBtnIconSize};
        height: ${sendBtnIconSize};
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

    // Build powered-by section
    const poweredByHtml = hideBranding
      ? ''
      : `<div class="chatevo-powered">Powered by <a href="https://chatevo.com" target="_blank">ChatEvo</a></div>`;

    // Create widget
    const container = document.createElement('div');
    container.className = 'chatevo-widget-container';
    container.innerHTML = `
      <button class="chatevo-toggle-btn" aria-label="Open chat">
        ${selectedIcon}
        ${closeIcon}
      </button>
      <div class="chatevo-modal">
        <div class="chatevo-header">
          <div class="chatevo-header-text">
            <div>
              <h3 class="chatevo-title">Chat Assistant</h3>
              ${showHeaderSubtitle && subtitleText ? `<p class="chatevo-subtitle">${subtitleText}</p>` : ''}
            </div>
          </div>
          <button class="chatevo-close-btn" aria-label="Close">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${isMinimal ? '2' : isBubbles ? '2.5' : '2'}"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
        <div class="chatevo-messages">
          ${(welcomeText || subtitleText) ? `<div class="chatevo-welcome ${suggestedMessages.length ? '' : 'chatevo-welcome-centered'}">
            ${welcomeText ? `<h4 class="chatevo-welcome-text">${welcomeText}</h4>` : ''}
            ${subtitleText ? `<p class="chatevo-welcome-sub">${subtitleText}</p>` : ''}
          </div>` : ''}
          <div class="chatevo-suggested" style="${suggestedMessages.length ? '' : 'display:none'}">
            ${suggestedMessages.map(msg => `<button class="chatevo-suggested-btn">${escapeHtml(msg)}</button>`).join('')}
          </div>
        </div>
        <div class="chatevo-input-area">
          <div class="chatevo-input-wrapper">
            <textarea class="chatevo-input" placeholder="${placeholderText}" rows="1"></textarea>
            <button class="chatevo-send-btn" disabled>
              ${sendIcon}
            </button>
          </div>
        </div>
        ${poweredByHtml}
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

    function openChat() {
      isOpen = true;
      modal.classList.add('open');
      toggleBtn.classList.add('open');
      setTimeout(() => input.focus(), 100);
      if (!companyInfo) fetchCompanyInfo();

    }

    function closeChat() {
      isOpen = false;
      modal.classList.remove('open');
      toggleBtn.classList.remove('open');
    }

    function toggleChat() {
      if (isOpen) closeChat();
      else openChat();
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function renderMarkdown(text) {
      let html = escapeHtml(text);

      // Code blocks
      html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (_m, _lang, code) =>
        `<pre class="ce-code-block"><code>${code.trim()}</code></pre>`
      );

      // Inline code
      html = html.replace(/`([^`]+)`/g, '<code class="ce-inline-code">$1</code>');

      // Bold
      html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

      // Italic (single * not adjacent to another *)
      html = html.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

      // Headings — render as bold text, not actual <h> tags (keeps it subtle in chat)
      html = html.replace(/^#{1,6}\s+(.+)$/gm, '<strong>$1</strong>');

      // Unordered list items
      html = html.replace(/^[*-]\s+(.+)$/gm, '<li>$1</li>');
      html = html.replace(/((?:<li>.*?<\/li>\s*)+)/g, '<ul class="ce-list">$1</ul>');

      // Ordered list items
      html = html.replace(/^\d+\.\s+(.+)$/gm, '<li>$1</li>');
      // Only wrap orphan <li> not already in <ul>
      html = html.replace(/(?<!<\/ul>)\s*((?:<li>.*?<\/li>\s*)+)/g, '<ol class="ce-list">$1</ol>');

      // Line breaks
      html = html.replace(/\n/g, '<br>');

      // Clean up <br> around block elements
      html = html.replace(/<br>\s*(<\/?(?:ul|ol|li|pre))/g, '$1');
      html = html.replace(/(<\/(?:ul|ol|pre)>)\s*<br>/g, '$1');

      return html;
    }

    function scrollToBottom() {
      messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function addBotMessage(content) {
      const welcome = messagesContainer.querySelector('.chatevo-welcome');
      if (welcome) welcome.remove();

      const div = document.createElement('div');
      div.className = 'chatevo-message bot-msg';

      div.innerHTML = `<div class="chatevo-message-content">${renderMarkdown(content)}</div>`;
      messagesContainer.appendChild(div);
      scrollToBottom();
      return div;
    }

    function addMessage(content, isUser = false) {
      if (!isUser) return addBotMessage(content);

      const welcome = messagesContainer.querySelector('.chatevo-welcome');
      if (welcome) welcome.remove();

      const div = document.createElement('div');
      div.className = 'chatevo-message user';
      div.innerHTML = `<div class="chatevo-message-content">${escapeHtml(content)}</div>`;
      messagesContainer.appendChild(div);
      scrollToBottom();
      return div;
    }

    function showTyping() {
      const div = document.createElement('div');
      div.className = 'chatevo-message bot-msg';
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
      hideSuggested();

      addMessage(message, true);
      showTyping();

      try {
        const response = await fetch(`${apiUrl}/public/chatbot/${companySlug}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message, chat_id: chatId })
        });

        if (!response.ok) throw new Error('Failed');

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
                  fullResponse += data.content;
                  if (!aiDiv) {
                    // Replace typing indicator in-place to avoid any gap
                    const typingEl = document.getElementById('chatevo-typing');
                    if (typingEl) {
                      typingEl.removeAttribute('id');
                      typingEl.innerHTML = `<div class="chatevo-message-content"></div>`;
                      aiDiv = typingEl;
                    } else {
                      aiDiv = addBotMessage('');
                    }
                  }
                  aiDiv.querySelector('.chatevo-message-content').innerHTML = renderMarkdown(fullResponse) + '<span class="chatevo-cursor"></span>';
                  scrollToBottom();
                } else if (data.type === 'end' && aiDiv) {
                  // Final render without cursor
                  aiDiv.querySelector('.chatevo-message-content').innerHTML = renderMarkdown(fullResponse);

                } else if (data.type === 'error') {
                  throw new Error(data.error);
                }
              } catch (e) {}
            }
          }
        }

        // Safety: hide typing if no chunks arrived
        hideTyping();

        messages.push({ role: 'user', content: message });
        messages.push({ role: 'assistant', content: fullResponse });

      } catch (e) {
        hideTyping();
        addBotMessage('Sorry, something went wrong. Please try again.');
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

    // Suggested messages
    const suggestedContainer = container.querySelector('.chatevo-suggested');
    function hideSuggested() {
      if (suggestedContainer) suggestedContainer.style.display = 'none';
    }

    container.querySelectorAll('.chatevo-suggested-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        input.value = btn.textContent;
        hideSuggested();
        sendMessage();
      });
    });

    // Events
    toggleBtn.addEventListener('click', toggleChat);
    closeBtn.addEventListener('click', closeChat);
    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('input', () => { updateSendButton(); autoResize(); });
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen) closeChat(); });

    fetchCompanyInfo();

    // Auto-open after delay
    if (autoOpenDelay > 0) {
      setTimeout(() => {
        if (!isOpen) openChat();
      }, autoOpenDelay * 1000);
    }
  }

  // Start loading
  loadAndInit();
})();
