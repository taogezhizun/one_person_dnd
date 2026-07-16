      (function () {
        const SIDEBAR_STORAGE_KEY = "one_person_dnd.sidebarCollapsed";
        const GAME_LAYOUT_WIDTH_STORAGE_PREFIX = "one_person_dnd.gameSidebarWidth.";
        const CHAT_HISTORY_HEIGHT_STORAGE_PREFIX = "one_person_dnd.chatHistoryHeight.";
        const ADVANCED_STORAGE_KEY = "one_person_dnd.advancedInputsOpen";
        const TURN_DRAFT_STORAGE_PREFIX = "one_person_dnd.turnDraft.";
        const STATE_BLOCK_DRAFT_STORAGE_PREFIX = "one_person_dnd.stateBlockDraft.";
        const SCROLL_BTN_ID = "scroll-to-bottom-btn";
        // Single source of truth for these five label maps is
        // `one_person_dnd.web.labels` (Python); base.html serializes them as
        // JSON into `#dnd-labels` before this script runs. A missing/invalid
        // element degrades gracefully to empty maps, which `labelForCode`
        // below already falls back from to the raw code (same as a stale
        // map would have done before this refactor).
        const LABEL_DATA = (function () {
          try {
            const el = document.getElementById("dnd-labels");
            return el ? JSON.parse(el.textContent || "{}") : {};
          } catch (e) {
            return {};
          }
        })();
        const ACTION_TYPE_LABELS = Object.freeze(LABEL_DATA.action_type || {});
        const ACTION_SIGNAL_LABELS = Object.freeze(LABEL_DATA.action_signal || {});
        const ACTION_WARNING_LABELS = Object.freeze(LABEL_DATA.action_warning || {});
        const CRITIC_WARNING_LABELS = Object.freeze(LABEL_DATA.critic_warning || {});
        const RESPONSE_WARNING_LABELS = Object.freeze(LABEL_DATA.response_warning || {});

        function labelForCode(labels, code) {
          if (!code) return "";
          return Object.prototype.hasOwnProperty.call(labels, code) ? labels[code] : code;
        }

        function setPillCode(pill, code, labels, prefix) {
          const display = labelForCode(labels, code);
          if (!display) return false;
          pill.textContent = (prefix || "") + display;
          pill.title = code;
          return true;
        }

        function renderMarkdown(root) {
          const scope = root || document;
          if (!window.marked || !window.DOMPurify) return;
          scope.querySelectorAll("[data-md]").forEach((el) => {
            const src = el.textContent || "";
            const html = window.marked.parse(src, { mangle: false, headerIds: false });
            el.innerHTML = window.DOMPurify.sanitize(html);
            el.removeAttribute("data-md");
          });
        }

        function initSkipLinks() {
          document.querySelectorAll("[data-skip-link]").forEach((link) => {
            link.addEventListener("click", function (evt) {
              const href = link.getAttribute("href") || "";
              if (!href.startsWith("#")) return;
              const target = document.getElementById(href.slice(1));
              if (!target) return;
              evt.preventDefault();
              try {
                target.focus({ preventScroll: true });
              } catch (e) {
                target.focus();
              }
              target.scrollIntoView({ block: "start" });
              if (window.history && window.history.pushState) {
                window.history.pushState(null, "", href);
              } else {
                window.location.hash = href;
              }
            });
          });
        }

        function scrollChatToBottom() {
          const el = document.getElementById("chat-history");
          if (!el) return;
          el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
        }

        function isNearBottom(el, thresholdPx) {
          if (!el) return true;
          const threshold = typeof thresholdPx === "number" ? thresholdPx : 120;
          const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
          return dist <= threshold;
        }

        let scrollBtnEl = null;
        let shouldFollowScroll = true; // follow only when user was already near bottom
        let hasUnreadNewContent = false;
        let pendingAutoScroll = false;
        let lastTurnShouldFollowScroll = true; // for non-stream (htmx) fallback

        function ensureScrollButton() {
          if (scrollBtnEl) return scrollBtnEl;
          const btn = document.createElement("button");
          btn.type = "button";
          btn.id = SCROLL_BTN_ID;
          btn.className = "scroll-bottom-btn";
          btn.style.display = "none";
          btn.textContent = "回到底部";
          btn.addEventListener("click", function () {
            const chat = document.getElementById("chat-history");
            if (!chat) return;
            hasUnreadNewContent = false;
            shouldFollowScroll = true;
            updateScrollButton();
            chat.scrollTo({ top: chat.scrollHeight, behavior: "smooth" });
          });
          document.body.appendChild(btn);
          scrollBtnEl = btn;
          return btn;
        }

        function updateScrollButton() {
          const chat = document.getElementById("chat-history");
          const btn = ensureScrollButton();
          if (!chat) {
            btn.style.display = "none";
            return;
          }
          const near = isNearBottom(chat, 120);
          if (near) {
            btn.style.display = "none";
            hasUnreadNewContent = false;
            return;
          }
          btn.style.display = "inline-flex";
          btn.textContent = hasUnreadNewContent ? "有新消息 · 回到底部" : "回到底部";
        }

        function scheduleAutoScroll() {
          if (pendingAutoScroll) return;
          pendingAutoScroll = true;
          requestAnimationFrame(() => {
            pendingAutoScroll = false;
            const chat = document.getElementById("chat-history");
            if (!chat) return;
            if (!shouldFollowScroll) return;
            chat.scrollTo({ top: chat.scrollHeight, behavior: "auto" });
            updateScrollButton();
          });
        }

        function setSidebarCollapsed(collapsed) {
          const body = document.body;
          if (!body) return;
          if (collapsed) body.classList.add("sidebar-collapsed");
          else body.classList.remove("sidebar-collapsed");
          try {
            localStorage.setItem(SIDEBAR_STORAGE_KEY, collapsed ? "1" : "0");
          } catch (e) {}

          const btn = document.querySelector("[data-sidebar-toggle]");
          if (btn) btn.textContent = collapsed ? "展开冒险面板" : "收起冒险面板";
        }

        function initSidebarToggle() {
          const btn = document.querySelector("[data-sidebar-toggle]");
          if (!btn) return;
          try {
            const saved = localStorage.getItem(SIDEBAR_STORAGE_KEY);
            if (saved === "1") setSidebarCollapsed(true);
          } catch (e) {}
          btn.addEventListener("click", function () {
            const collapsed = document.body.classList.contains("sidebar-collapsed");
            setSidebarCollapsed(!collapsed);
          });
        }

        function gameLayoutStorageKey(grid) {
          const sessionInput = grid ? grid.querySelector("input[name=session_id]") : null;
          const sessionId = sessionInput && sessionInput.value ? sessionInput.value : "current";
          return GAME_LAYOUT_WIDTH_STORAGE_PREFIX + sessionId;
        }

        function canResizeGameLayout(grid, resizer) {
          if (!grid || !resizer) return false;
          if (document.body.classList.contains("sidebar-collapsed")) return false;
          return window.getComputedStyle(resizer).display !== "none";
        }

        function clampGameSidebarWidth(grid, width) {
          const rect = grid.getBoundingClientRect();
          const sidebarMin = grid.classList.contains("grid--game-story-first") ? 340 : 360;
          const storyMin = grid.classList.contains("grid--game-story-first") ? 560 : 620;
          const maxByGrid = Math.max(sidebarMin, rect.width - storyMin - 32);
          const sidebarMax = Math.min(520, maxByGrid);
          const numeric = Number.parseFloat(width);
          if (!Number.isFinite(numeric)) return sidebarMin;
          return Math.max(sidebarMin, Math.min(sidebarMax, numeric));
        }

        function applyGameSidebarWidth(grid, width, persist) {
          if (!grid) return;
          const nextWidth = clampGameSidebarWidth(grid, width);
          grid.style.setProperty("--game-sidebar-width", nextWidth + "px");
          if (persist) {
            try {
              localStorage.setItem(gameLayoutStorageKey(grid), String(Math.round(nextWidth)));
            } catch (e) {}
          }
        }

        function resetGameLayoutWidth(grid) {
          if (!grid) return;
          grid.style.removeProperty("--game-sidebar-width");
          try {
            localStorage.removeItem(gameLayoutStorageKey(grid));
          } catch (e) {}
        }

        function initGameLayoutResizer() {
          const grid = document.querySelector("[data-game-layout]");
          const resizer = document.querySelector("[data-game-layout-resizer]");
          const resetBtn = document.querySelector("[data-game-layout-reset]");
          if (!grid || !resizer) return;

          try {
            const saved = localStorage.getItem(gameLayoutStorageKey(grid));
            if (saved) applyGameSidebarWidth(grid, Number.parseFloat(saved), false);
          } catch (e) {}

          let dragActive = false;
          let lastPointerDownAt = 0;
          function widthFromPointer(evt) {
            const rect = grid.getBoundingClientRect();
            return rect.right - evt.clientX;
          }

          resizer.addEventListener("pointerdown", function (evt) {
            if (!canResizeGameLayout(grid, resizer)) return;
            const now = Date.now();
            if (now - lastPointerDownAt < 360) {
              lastPointerDownAt = 0;
              resetGameLayoutWidth(grid);
              evt.preventDefault();
              return;
            }
            lastPointerDownAt = now;
            dragActive = true;
            document.body.classList.add("game-layout-resizing");
            try {
              resizer.setPointerCapture(evt.pointerId);
            } catch (e) {}
            evt.preventDefault();
          });

          window.addEventListener("pointermove", function (evt) {
            if (!dragActive) return;
            applyGameSidebarWidth(grid, widthFromPointer(evt), true);
          });

          window.addEventListener("pointerup", function () {
            if (!dragActive) return;
            dragActive = false;
            document.body.classList.remove("game-layout-resizing");
          });

          resizer.addEventListener("keydown", function (evt) {
            if (!canResizeGameLayout(grid, resizer)) return;
            if (evt.key !== "ArrowLeft" && evt.key !== "ArrowRight") return;
            const current = Number.parseFloat(window.getComputedStyle(grid).getPropertyValue("--game-sidebar-width"));
            const delta = evt.shiftKey ? 48 : 16;
            applyGameSidebarWidth(grid, current + (evt.key === "ArrowLeft" ? delta : -delta), true);
            evt.preventDefault();
          });

          resizer.addEventListener("dblclick", function () {
            resetGameLayoutWidth(grid);
          });

          if (resetBtn) {
            resetBtn.addEventListener("click", function () {
              resetGameLayoutWidth(grid);
            });
          }

          window.addEventListener("resize", function () {
            const current = Number.parseFloat(window.getComputedStyle(grid).getPropertyValue("--game-sidebar-width"));
            if (Number.isFinite(current)) applyGameSidebarWidth(grid, current, false);
          });
        }

        function chatHistoryHeightStorageKey() {
          const sessionInput = document.querySelector("#turn-form input[name=session_id], input[name=session_id], select[name=session_id]");
          const sessionId = sessionInput && sessionInput.value ? sessionInput.value : "current";
          return CHAT_HISTORY_HEIGHT_STORAGE_PREFIX + sessionId;
        }

        function clampChatHistoryHeight(chat, height) {
          const minHeight = window.matchMedia("(max-width: 520px)").matches ? 150 : 220;
          const maxHeight = Math.min(920, Math.max(minHeight, window.innerHeight - 156));
          const numeric = Number.parseFloat(height);
          if (!Number.isFinite(numeric)) {
            const current = chat ? chat.getBoundingClientRect().height : minHeight;
            return Math.max(minHeight, Math.min(maxHeight, current));
          }
          return Math.max(minHeight, Math.min(maxHeight, numeric));
        }

        function applyChatHistoryHeight(chat, height, persist) {
          if (!chat) return;
          const nextHeight = clampChatHistoryHeight(chat, height);
          const card = chat.closest(".chat-card");
          if (card) card.classList.add("chat-card--history-resized");
          chat.style.setProperty("--chat-history-height", nextHeight + "px");
          chat.dataset.chatHistoryHeight = String(Math.round(nextHeight));
          if (persist) {
            try {
              localStorage.setItem(chatHistoryHeightStorageKey(), String(Math.round(nextHeight)));
            } catch (e) {}
          }
        }

        function resetChatHistoryHeight(chat) {
          if (!chat) return;
          const card = chat.closest(".chat-card");
          if (card) card.classList.remove("chat-card--history-resized");
          chat.style.removeProperty("--chat-history-height");
          delete chat.dataset.chatHistoryHeight;
          try {
            localStorage.removeItem(chatHistoryHeightStorageKey());
          } catch (e) {}
        }

        function canResizeChatHistory(resizer) {
          return Boolean(resizer && window.getComputedStyle(resizer).display !== "none");
        }

        function initChatHistoryResizer() {
          const chat = document.querySelector("[data-chat-history-resizable]");
          const resizer = document.querySelector("[data-chat-history-resizer]");
          const resetBtn = document.querySelector("[data-game-layout-reset]");
          if (!chat || !resizer) return;

          try {
            const saved = localStorage.getItem(chatHistoryHeightStorageKey());
            if (saved && canResizeChatHistory(resizer)) applyChatHistoryHeight(chat, Number.parseFloat(saved), false);
          } catch (e) {}

          let dragActive = false;
          let lastPointerDownAt = 0;
          function heightFromPointer(evt) {
            const rect = chat.getBoundingClientRect();
            return evt.clientY - rect.top;
          }

          resizer.addEventListener("pointerdown", function (evt) {
            if (!canResizeChatHistory(resizer)) return;
            const now = Date.now();
            if (now - lastPointerDownAt < 360) {
              lastPointerDownAt = 0;
              resetChatHistoryHeight(chat);
              evt.preventDefault();
              return;
            }
            lastPointerDownAt = now;
            dragActive = true;
            document.body.classList.add("chat-history-resizing");
            try {
              resizer.setPointerCapture(evt.pointerId);
            } catch (e) {}
            evt.preventDefault();
          });

          window.addEventListener("pointermove", function (evt) {
            if (!dragActive) return;
            applyChatHistoryHeight(chat, heightFromPointer(evt), true);
          });

          window.addEventListener("pointerup", function () {
            if (!dragActive) return;
            dragActive = false;
            document.body.classList.remove("chat-history-resizing");
          });

          resizer.addEventListener("keydown", function (evt) {
            if (!canResizeChatHistory(resizer)) return;
            if (evt.key !== "ArrowUp" && evt.key !== "ArrowDown") return;
            const current = Number.parseFloat(chat.dataset.chatHistoryHeight || chat.getBoundingClientRect().height);
            const delta = evt.shiftKey ? 48 : 16;
            applyChatHistoryHeight(chat, current + (evt.key === "ArrowDown" ? delta : -delta), true);
            evt.preventDefault();
          });

          resizer.addEventListener("dblclick", function () {
            resetChatHistoryHeight(chat);
          });

          if (resetBtn) {
            resetBtn.addEventListener("click", function () {
              resetChatHistoryHeight(chat);
            });
          }

          window.addEventListener("resize", function () {
            if (!canResizeChatHistory(resizer)) {
              const card = chat.closest(".chat-card");
              if (card) card.classList.remove("chat-card--history-resized");
              chat.style.removeProperty("--chat-history-height");
              delete chat.dataset.chatHistoryHeight;
              return;
            }
            const current = Number.parseFloat(chat.dataset.chatHistoryHeight || "");
            if (Number.isFinite(current)) applyChatHistoryHeight(chat, current, false);
          });
        }

        function initAdvancedInputsToggle() {
          const details = document.querySelector("[data-advanced-inputs]");
          if (!details) return;
          const form = document.getElementById("turn-form");
          try {
            const saved = localStorage.getItem(ADVANCED_STORAGE_KEY);
            const compactStory = Boolean(details.closest(".chat-card--story-first"));
            if (saved === "1" && (!compactStory || hasStateBlockDraft(form))) details.open = true;
          } catch (e) {}
          details.addEventListener("toggle", function () {
            try {
              localStorage.setItem(ADVANCED_STORAGE_KEY, details.open ? "1" : "0");
            } catch (e) {}
          });
        }

        function sessionScopedDraftKey(form, prefix) {
          const sessionInput = form ? form.querySelector("input[name=session_id]") : null;
          const sessionId = sessionInput && sessionInput.value ? sessionInput.value : "current";
          return prefix + sessionId;
        }

        function turnDraftKey(form) {
          return sessionScopedDraftKey(form, TURN_DRAFT_STORAGE_PREFIX);
        }

        function stateBlockDraftKey(form) {
          return sessionScopedDraftKey(form, STATE_BLOCK_DRAFT_STORAGE_PREFIX);
        }

        function hasStateBlockDraft(form) {
          try {
            return Boolean(localStorage.getItem(stateBlockDraftKey(form)));
          } catch (e) {
            return false;
          }
        }

        function clearTurnDraft(form) {
          try {
            localStorage.removeItem(turnDraftKey(form));
          } catch (e) {}
        }

        function clearStateBlockDraft(form) {
          try {
            localStorage.removeItem(stateBlockDraftKey(form));
          } catch (e) {}
        }

        function resizeAutoGrowTextarea(ta) {
          if (!ta) return;
          ta.style.height = "auto";
          const maxHeight = Number.parseFloat(window.getComputedStyle(ta).maxHeight) || 260;
          const nextHeight = Math.min(ta.scrollHeight, maxHeight);
          ta.style.height = nextHeight + "px";
          ta.style.overflowY = ta.scrollHeight > maxHeight ? "auto" : "hidden";
        }

        function initAutoGrowTextareas() {
          document.querySelectorAll("textarea[data-autogrow]").forEach((ta) => {
            resizeAutoGrowTextarea(ta);
            ta.addEventListener("input", function () {
              resizeAutoGrowTextarea(ta);
            });
          });
        }

        function initTurnDraftPersistence() {
          const form = document.getElementById("turn-form");
          if (!form) return;
          const ta = form.querySelector("textarea[name=player_text]");
          if (!ta) return;

          try {
            const saved = localStorage.getItem(turnDraftKey(form));
            if (saved && !ta.value.trim()) {
              ta.value = saved;
              resizeAutoGrowTextarea(ta);
              showTurnDraftFeedback();
            }
          } catch (e) {}

          ta.addEventListener("input", function () {
            try {
              if (ta.value.trim()) localStorage.setItem(turnDraftKey(form), ta.value);
              else localStorage.removeItem(turnDraftKey(form));
            } catch (e) {}
          });
        }

        function initStateBlockDraftPersistence() {
          const form = document.getElementById("turn-form");
          if (!form) return;
          const stateBlock = form.querySelector("textarea[name=state_block]");
          if (!stateBlock) return;

          try {
            const saved = localStorage.getItem(stateBlockDraftKey(form));
            if (saved && !stateBlock.value.trim()) {
              stateBlock.value = saved;
              showTurnContextFeedback(saved.trim());
              revealTurnContextInput(stateBlock);
            }
          } catch (e) {}

          stateBlock.addEventListener("input", function () {
            try {
              if (stateBlock.value.trim()) localStorage.setItem(stateBlockDraftKey(form), stateBlock.value);
              else localStorage.removeItem(stateBlockDraftKey(form));
            } catch (e) {}
          });
        }

        function hasUnsavedTurnDraft(form) {
          if (!form) return false;
          if (form.dataset.turnInFlight === "1") return false;
          const playerText = form.querySelector("textarea[name=player_text]");
          const stateBlock = form.querySelector("textarea[name=state_block]");
          const hasPlayerText = Boolean(playerText && playerText.value.trim());
          const hasStateBlock = Boolean(stateBlock && stateBlock.value.trim());
          return hasPlayerText || hasStateBlock;
        }

        function initUnsavedTurnWarning() {
          const form = document.getElementById("turn-form");
          if (!form) return;
          window.addEventListener("beforeunload", function (evt) {
            if (!hasUnsavedTurnDraft(form)) return;
            evt.preventDefault();
            evt.returnValue = "";
          });
        }

        function isTurnRequestInFlight() {
          const form = document.getElementById("turn-form");
          return Boolean(form && form.dataset.turnInFlight === "1");
        }

        function setTurnFieldsReadOnly(form, readOnly) {
          if (!form) return;
          form.querySelectorAll("[data-turn-lockable]").forEach((field) => {
            field.readOnly = readOnly;
            field.setAttribute("aria-readonly", readOnly ? "true" : "false");
          });
        }

        function updateTurnSubmitState(form) {
          const submitBtn = form ? form.querySelector("[data-turn-submit]") : null;
          if (!submitBtn) return;
          const ta = form.querySelector("textarea[name=player_text]");
          const hasText = Boolean(ta && ta.value.trim());
          const llmReady = form.dataset.llmReady !== "0";
          const loading = form.dataset.turnInFlight === "1";
          const defaultLabel = submitBtn.dataset.defaultLabel || "发送";
          const loadingLabel = submitBtn.dataset.loadingLabel || defaultLabel;
          submitBtn.textContent = loading ? loadingLabel : defaultLabel;
          submitBtn.disabled = loading || !hasText || !llmReady;
        }

        function initTurnSubmitState() {
          const form = document.getElementById("turn-form");
          if (!form) return;
          const ta = form.querySelector("textarea[name=player_text]");
          if (!ta) return;
          ta.addEventListener("input", function () {
            syncSelectedChoiceWithInput(form);
            updateTurnSubmitState(form);
          });
          updateTurnSubmitState(form);
        }

        function updateQuickRollSubmitState(form) {
          if (!form) return;
          const input = form.querySelector("[data-quick-roll-input]");
          const submitBtn = form.querySelector("[data-quick-roll-submit]");
          if (!input || !submitBtn) return;
          const hasExpr = Boolean(input.value.trim());
          const loading = form.dataset.quickRollInFlight === "1";
          submitBtn.disabled = loading || !hasExpr;
        }

        function setQuickRollRequestUI(form, inFlight) {
          if (!form) return;
          const input = form.querySelector("[data-quick-roll-input]");
          form.dataset.quickRollInFlight = inFlight ? "1" : "0";
          if (input) {
            input.readOnly = inFlight;
            input.setAttribute("aria-readonly", inFlight ? "true" : "false");
          }
          updateQuickRollSubmitState(form);
        }

        function initQuickRollSubmitState() {
          document.querySelectorAll("[data-quick-roll-submit]").forEach((submitBtn) => {
            const form = submitBtn.closest("form");
            const input = form ? form.querySelector("[data-quick-roll-input]") : null;
            if (!form || !input) return;
            input.addEventListener("input", function () {
              updateQuickRollSubmitState(form);
            });
            updateQuickRollSubmitState(form);
          });
        }

        function initLongSubmitForms() {
          document.querySelectorAll("[data-long-submit]").forEach((form) => {
            form.addEventListener("submit", function (event) {
              const submittedButton = event.submitter;
              const button = submittedButton && submittedButton.matches("[data-long-submit-button]")
                ? submittedButton
                : form.querySelector("[data-long-submit-button]");
              const status = form.querySelector("[data-long-submit-status]");
              if (button) {
                const loadingLabel = button.dataset.longSubmitLabel || button.textContent || "";
                if (loadingLabel) button.textContent = loadingLabel;
                button.disabled = true;
              }
              if (status) status.hidden = false;
            });
          });
        }

        function initConfirmForms() {
          document.body.addEventListener("submit", function (event) {
            const form = event.target instanceof HTMLFormElement ? event.target : null;
            if (!form || !form.dataset.confirmMessage) return;
            if (!window.confirm(form.dataset.confirmMessage)) event.preventDefault();
          });
        }

        function setTurnRequestUI(inFlight) {
          const form = document.getElementById("turn-form");
          const cancelBtn = document.getElementById("turn-cancel");
          if (cancelBtn) cancelBtn.hidden = !inFlight;
          if (form) {
            form.dataset.turnInFlight = inFlight ? "1" : "0";
            setTurnFieldsReadOnly(form, inFlight);
            updateTurnSubmitState(form);
          }
        }

        let currentTurnAbortController = null;

        function abortTurnRequest() {
          if (currentTurnAbortController) {
            try {
              currentTurnAbortController.abort();
            } catch (e) {}
            currentTurnAbortController = null;
            setTurnRequestUI(false);
            return;
          }
          const form = document.getElementById("turn-form");
          if (!form || !window.htmx) return;
          try {
            window.htmx.abort(form);
          } catch (e) {}
          setTurnRequestUI(false);
        }

        function appendTurnSkeleton(chatHistory, playerText) {
          const turnEl = document.createElement("div");
          turnEl.className = "chat__turn";

          const userMsg = document.createElement("div");
          userMsg.className = "chat__msg chat__msg--user";
          userMsg.innerHTML = '<div class="chat__meta">你</div>';
          const userContent = document.createElement("div");
          userContent.className = "chat__content pre";
          userContent.textContent = playerText || "";
          userMsg.appendChild(userContent);

          const asstMsg = document.createElement("div");
          asstMsg.className = "chat__msg chat__msg--assistant";
          asstMsg.innerHTML = '<div class="chat__meta">DM</div>';
          const asstContent = document.createElement("div");
          asstContent.className = "chat__content pre streaming-wait spinner";
          asstContent.id = "streaming-dm";
          asstContent.dataset.waiting = "1";
          asstContent.setAttribute("role", "status");
          asstContent.setAttribute("aria-live", "polite");
          asstContent.textContent = "DM 正在思考下一幕…";
          asstMsg.appendChild(asstContent);

          turnEl.appendChild(userMsg);
          turnEl.appendChild(asstMsg);
          chatHistory.appendChild(turnEl);
          return { turnEl, asstContent };
        }

        function renderTurnRequestNotice(turnEl, title, message, warn) {
          const asstMsg = turnEl ? turnEl.querySelector(".chat__msg--assistant") : null;
          if (!asstMsg) return;

          asstMsg.innerHTML = '';
          const meta = document.createElement("div");
          meta.className = "chat__meta";
          meta.textContent = "DM";
          asstMsg.appendChild(meta);

          const notice = document.createElement("div");
          notice.className = warn ? "notice notice--err" : "notice";
          notice.setAttribute("role", "status");
          notice.setAttribute("aria-live", "polite");

          const titleEl = document.createElement("div");
          titleEl.style.fontWeight = "700";
          titleEl.textContent = title || "请求状态";
          notice.appendChild(titleEl);

          const msgEl = document.createElement("div");
          msgEl.className = "muted";
          msgEl.textContent = message || "";
          notice.appendChild(msgEl);

          asstMsg.appendChild(notice);
        }

        function refreshCharacterPanel() {
          const panel = document.getElementById("character-panel");
          if (!panel || !window.htmx) return;
          window.htmx.ajax("GET", "/character/panel", {
            target: "#character-panel",
            swap: "innerHTML",
          });
        }

        function setPendingReviewCount(count) {
          const next = Math.max(0, Number(count || 0));
          document.querySelectorAll("[data-pending-count]").forEach((el) => {
            el.textContent = String(next);
          });
          document.querySelectorAll("[data-pending-pill]").forEach((el) => {
            el.hidden = next <= 0;
          });

          const callout = document.querySelector("[data-review-callout]");
          if (callout) callout.hidden = next <= 0;
          const text = document.querySelector("[data-review-callout-text]");
          if (text) {
            text.textContent =
              `有 ${next} 条 DM 建议待确认。应用前可先查看预览；角色状态和剧情线不会自动改写。`;
          }
        }

        function surfacePendingReview(turn) {
          if (!(turn && turn.has_pending_review)) return;
          const countEl = document.querySelector("[data-pending-count]");
          const current = countEl ? Number((countEl.textContent || "0").replace(/\D+/g, "")) || 0 : 0;
          const delta = Math.max(1, Number(turn.pending_review_delta || 1));
          setPendingReviewCount(current + delta);
        }

        function syncPendingReviewCountFromPanel() {
          const marker = document.querySelector("[data-character-pending-count]");
          if (!marker) return;
          const count = Number(marker.dataset.characterPendingCount || marker.textContent || 0);
          setPendingReviewCount(count);
        }

        function renderActionAssessment(targetEl, assessment) {
          if (!targetEl || !assessment) return;
          const previous = targetEl.querySelector(".action-assessment");
          if (previous) previous.remove();

          const wrap = document.createElement("div");
          wrap.className = "action-assessment";
          const label = document.createElement("div");
          label.className = "muted action-assessment__label";
          label.textContent = "系统判定";
          wrap.appendChild(label);

          const pills = document.createElement("div");
          pills.className = "assessment-pills";
          const addPill = function (code, warn, labels, prefix) {
            const pill = document.createElement("span");
            pill.className = warn ? "assessment-pill assessment-pill--warn" : "assessment-pill";
            if (!setPillCode(pill, code, labels, prefix)) return;
            pills.appendChild(pill);
          };
          addPill(assessment.action_type, false, ACTION_TYPE_LABELS, "行动：");
          const signals = Array.isArray(assessment.signals) ? assessment.signals : [];
          const warnings = Array.isArray(assessment.warnings) ? assessment.warnings : [];
          signals.forEach((s) => addPill(s, false, ACTION_SIGNAL_LABELS, ""));
          warnings.forEach((w) => addPill(w, true, ACTION_WARNING_LABELS, ""));
          wrap.appendChild(pills);
          targetEl.appendChild(wrap);
        }

        function renderDmReview(targetEl, criticWarnings) {
          if (!targetEl) return;
          const warnings = Array.isArray(criticWarnings) ? criticWarnings : [];
          if (warnings.length === 0) return;

          const wrap = document.createElement("div");
          wrap.className = "dm-review";
          const label = document.createElement("div");
          label.className = "muted dm-review__label";
          label.textContent = "DM 审查";
          wrap.appendChild(label);

          const pills = document.createElement("div");
          pills.className = "assessment-pills";
          warnings.forEach((w) => {
            if (!w) return;
            const pill = document.createElement("span");
            pill.className = "assessment-pill assessment-pill--warn";
            setPillCode(pill, w, CRITIC_WARNING_LABELS, "");
            pills.appendChild(pill);
          });
          wrap.appendChild(pills);
          targetEl.appendChild(wrap);
        }

        function renderResponseReview(targetEl, responseWarnings) {
          if (!targetEl) return;
          const warnings = Array.isArray(responseWarnings) ? responseWarnings : [];
          if (warnings.length === 0) return;

          const wrap = document.createElement("div");
          wrap.className = "response-review";
          const label = document.createElement("div");
          label.className = "muted response-review__label";
          label.textContent = "反应评估";
          wrap.appendChild(label);

          const pills = document.createElement("div");
          pills.className = "assessment-pills";
          warnings.forEach((w) => {
            if (!w) return;
            const pill = document.createElement("span");
            pill.className = "assessment-pill assessment-pill--warn";
            setPillCode(pill, w, RESPONSE_WARNING_LABELS, "");
            pills.appendChild(pill);
          });
          wrap.appendChild(pills);
          targetEl.appendChild(wrap);
        }

        function renderLatestChoices(choices) {
          const tray = document.querySelector("[data-latest-choices]");
          const list = tray ? tray.querySelector("[data-latest-choices-list]") : null;
          if (!tray || !list) return;
          const items = Array.isArray(choices) ? choices.filter((item) => String(item || "").trim()) : [];
          list.innerHTML = "";
          items.forEach((choice) => {
            const text = String(choice || "").trim();
            const button = document.createElement("button");
            button.type = "button";
            button.className = "choice-action choice-action--latest";
            button.dataset.choiceText = text;
            button.title = text;
            button.setAttribute("data-choice-action", "");
            button.setAttribute("aria-pressed", "false");
            button.textContent = text;
            list.appendChild(button);
          });
          tray.hidden = items.length === 0;
        }

        function syncLatestChoicesFromTurn(turnEl) {
          if (!turnEl) return;
          const choices = Array.from(turnEl.querySelectorAll("[data-turn-choice-history] [data-choice-action]"))
            .map((button) => (button.dataset.choiceText || button.textContent || "").trim())
            .filter(Boolean);
          renderLatestChoices(choices);
        }

        function renderSystemDiagnostic(turn) {
          const root = document.getElementById("system-diagnostics");
          if (!root || !turn) return;
          const criticWarnings = Array.isArray(turn.critic_warnings) ? turn.critic_warnings : [];
          const responseWarnings = Array.isArray(turn.response_warnings) ? turn.response_warnings : [];
          const dmNotes = (turn.dm && turn.dm.dm_notes) || "";
          const memorySuggestions = (turn.dm && turn.dm.memory_suggestions) || "";
          if (!criticWarnings.length && !responseWarnings.length && !dmNotes.trim() && !memorySuggestions.trim()) return;

          const turnIndex = String(turn.turn_index ?? "最新");
          const previous = root.querySelector(`[data-turn-diagnostic="${CSS.escape(turnIndex)}"]`);
          if (previous) previous.remove();

          const article = document.createElement("article");
          article.className = "turn-diagnostic";
          article.dataset.turnDiagnostic = turnIndex;
          const head = document.createElement("div");
          head.className = "turn-diagnostic__head";
          const title = document.createElement("strong");
          title.textContent = `回合 ${turnIndex}`;
          head.appendChild(title);
          article.appendChild(head);

          renderDmReview(article, criticWarnings);
          renderResponseReview(article, responseWarnings);
          if (!criticWarnings.length && !responseWarnings.length) {
            const passed = document.createElement("div");
            passed.className = "muted";
            passed.textContent = "可玩性检查通过";
            article.appendChild(passed);
          }
          const addDetails = function (label, content) {
            if (!content || !content.trim()) return;
            const details = document.createElement("details");
            const summary = document.createElement("summary");
            summary.textContent = label;
            const body = document.createElement("div");
            body.className = "prose-copy";
            body.textContent = content;
            details.appendChild(summary);
            details.appendChild(body);
            article.appendChild(details);
          };
          addDetails("DM 内部备注", dmNotes);
          addDetails("故事记忆建议", memorySuggestions);
          root.prepend(article);
        }

        function renderRecalledContext(recalledContext, recalledWorld) {
          const recall = document.getElementById("recall-preview");
          if (!recall) return;
          recall.innerHTML = "";

          const contextItems = Array.isArray(recalledContext) ? recalledContext : [];
          if (contextItems.length > 0) {
            const details = document.createElement("details");
            details.className = "recall-panel";
            details.open = true;
            const summary = document.createElement("summary");
            summary.className = "muted";
            summary.textContent = "本回合参考";
            details.appendChild(summary);

            const ol = document.createElement("ol");
            ol.className = "recall-stack";
            contextItems.forEach((item) => {
              const isSkipped = item && item.status === "skipped";
              const li = document.createElement("li");
              li.className = isSkipped ? "recall-item recall-item--skipped" : "recall-item";

              const head = document.createElement("div");
              head.className = "recall-item__head";
              const title = document.createElement("span");
              title.className = "recall-item__title";
              title.textContent = item.title || item.kind || "Context";
              const meta = document.createElement("span");
              meta.className = "muted";
              meta.textContent = `${item.kind || "context"} · ${item.source || "unknown"}`;
              head.appendChild(title);
              head.appendChild(meta);
              if (isSkipped) {
                const status = document.createElement("span");
                status.className = "recall-status recall-status--skipped";
                status.textContent = "已裁剪";
                head.appendChild(status);
              }
              li.appendChild(head);

              if (item.reason) {
                const reason = document.createElement("div");
                reason.className = "muted";
                reason.textContent = item.reason;
                li.appendChild(reason);
              }
              if (item.preview) {
                const preview = document.createElement("div");
                preview.className = "recall-item__preview";
                preview.textContent = item.preview;
                li.appendChild(preview);
              }
              ol.appendChild(li);
            });
            details.appendChild(ol);
            recall.appendChild(details);
            return;
          }

          const worldItems = Array.isArray(recalledWorld) ? recalledWorld : [];
          if (worldItems.length > 0) {
            const ol = document.createElement("ol");
            ol.className = "recall-stack";
            worldItems.forEach((e) => {
              const li = document.createElement("li");
              const t = document.createElement("span");
              t.className = "muted";
              t.textContent = `[${e.type}]`;
              li.appendChild(t);
              li.appendChild(document.createTextNode(" " + (e.title || "")));
              if (e.tags) {
                const s = document.createElement("span");
                s.className = "muted";
                s.textContent = `（${e.tags}）`;
                li.appendChild(document.createTextNode(" "));
                li.appendChild(s);
              }
              ol.appendChild(li);
            });
            recall.appendChild(ol);
          } else {
            recall.innerHTML = '<span class="muted">（本回合没有可显示的召回上下文；可以尝试填写更具体的标签或状态）</span>';
          }
        }

        function renderFinalTurn(turn, recalledWorld, recalledContext, turnEl) {
          const userMsg = turnEl.querySelector(".chat__msg--user");
          if (userMsg) renderActionAssessment(userMsg, turn && turn.action_assessment);

          const diceEvents = (turn && turn.dice_events) || [];
          if (userMsg && diceEvents && diceEvents.length > 0) {
            const wrap = document.createElement("div");
            wrap.className = "dice-events";
            const title = document.createElement("div");
            title.className = "muted";
            title.textContent = "系统掷骰";
            wrap.appendChild(title);
            const ul = document.createElement("ul");
            ul.className = "dice-events__list";
            diceEvents.forEach((e) => {
              const li = document.createElement("li");
              const expr = e.expr || "";
              const rolls = Array.isArray(e.rolls) ? e.rolls.join(", ") : "";
              const mod = Number(e.modifier || 0);
              const total = Number(e.total || 0);
              li.innerHTML = `<span class="muted">${expr}</span> =&gt; [${rolls}] ${mod >= 0 ? "+" + mod : mod} = <strong>${total}</strong>`;
              ul.appendChild(li);
            });
            wrap.appendChild(ul);
            userMsg.appendChild(wrap);
          }

          const asstMsg = turnEl.querySelector(".chat__msg--assistant");
          if (!asstMsg) return;
          asstMsg.innerHTML = '<div class="chat__meta">DM</div>';

          const narration = document.createElement("div");
          narration.className = "chat__content md";
          narration.setAttribute("data-md", "");
          narration.textContent = (turn.dm && turn.dm.narration) || "";
          asstMsg.appendChild(narration);

          const choices = (turn.dm && turn.dm.choices) || [];
          if (choices && choices.length > 0) {
            const wrap = document.createElement("details");
            wrap.className = "turn-choice-history";
            wrap.setAttribute("data-turn-choice-history", "");
            const summary = document.createElement("summary");
            summary.textContent = "当时的行动灵感";
            wrap.appendChild(summary);
            const list = document.createElement("div");
            list.className = "choices__list";
            choices.forEach((c) => {
              const btn = document.createElement("button");
              btn.type = "button";
              btn.className = "choice-action";
              btn.dataset.choiceText = c || "";
              btn.title = c || "";
              btn.setAttribute("data-choice-action", "");
              btn.setAttribute("aria-pressed", "false");
              btn.textContent = c;
              list.appendChild(btn);
            });
            wrap.appendChild(list);
            asstMsg.appendChild(wrap);
          }
          renderLatestChoices(choices);
          renderSystemDiagnostic(turn);
          renderRecalledContext(recalledContext, recalledWorld);
        }

        function focusPlayerActionInput() {
          const ta = document.querySelector("#turn-form textarea[name=player_text]");
          if (!ta) return null;
          ta.focus();
          try {
            ta.setSelectionRange(ta.value.length, ta.value.length);
          } catch (e) {}
          ta.scrollIntoView({ block: "center", behavior: "smooth" });
          return ta;
        }

        let choiceFeedbackTimer = null;

        function hideChoiceActionFeedback() {
          const feedback = document.querySelector("[data-choice-feedback]");
          if (!feedback) return;
          if (choiceFeedbackTimer) {
            window.clearTimeout(choiceFeedbackTimer);
            choiceFeedbackTimer = null;
          }
          feedback.hidden = true;
          feedback.textContent = "";
        }

        function showChoiceActionFeedback() {
          const feedback = document.querySelector("[data-choice-feedback]");
          if (!feedback) return;
          if (choiceFeedbackTimer) window.clearTimeout(choiceFeedbackTimer);
          feedback.textContent = "已填入行动，可直接发送";
          feedback.hidden = false;
          choiceFeedbackTimer = window.setTimeout(function () {
            feedback.hidden = true;
            choiceFeedbackTimer = null;
          }, 2200);
        }

        function showTurnDraftFeedback() {
          const feedback = document.querySelector("[data-choice-feedback]");
          if (!feedback) return;
          if (choiceFeedbackTimer) window.clearTimeout(choiceFeedbackTimer);
          feedback.textContent = "已恢复未发送的行动草稿，可继续编辑或发送";
          feedback.hidden = false;
          choiceFeedbackTimer = window.setTimeout(function () {
            feedback.hidden = true;
            choiceFeedbackTimer = null;
          }, 3200);
        }

        function hideTurnContextFeedback() {
          const feedback = document.querySelector("[data-turn-context-feedback]");
          if (!feedback) return;
          feedback.hidden = true;
          feedback.textContent = "";
        }

        function showTurnContextFeedback(context) {
          const feedback = document.querySelector("[data-turn-context-feedback]");
          if (!feedback) return;
          feedback.textContent = "已带入本回合线索：" + context;
          feedback.hidden = false;
        }

        function revealTurnContextInput(stateBlock) {
          if (!stateBlock) return;
          const advanced = stateBlock.closest("[data-advanced-inputs]");
          if (advanced) {
            advanced.open = true;
            try {
              localStorage.setItem(ADVANCED_STORAGE_KEY, "1");
            } catch (e) {}
          }
          try {
            stateBlock.focus({ preventScroll: true });
          } catch (e) {
            stateBlock.focus();
          }
          stateBlock.scrollIntoView({ block: "center", behavior: "smooth" });
        }

        function clearSelectedChoiceActions() {
          document.querySelectorAll("[data-choice-action][aria-pressed='true']").forEach((el) => {
            el.setAttribute("aria-pressed", "false");
            el.classList.remove("choice-action--selected");
          });
          hideChoiceActionFeedback();
        }

        function syncSelectedChoiceWithInput(form) {
          const selected = document.querySelector("[data-choice-action][aria-pressed='true']");
          if (!selected) return;
          const ta = form ? form.querySelector("textarea[name=player_text]") : null;
          const currentText = ta && ta.value ? ta.value.trim() : "";
          const selectedText = (selected.dataset.choiceText || selected.textContent || "").trim();
          if (!currentText || selectedText !== currentText) clearSelectedChoiceActions();
        }

        function selectChoiceAction(btn) {
          if (!btn) return;
          clearSelectedChoiceActions();
          btn.setAttribute("aria-pressed", "true");
          btn.classList.add("choice-action--selected");
        }

        function initChoiceActions() {
          document.body.addEventListener("click", function (evt) {
            const target = evt.target instanceof Element ? evt.target : null;
            const btn = target ? target.closest("[data-choice-action]") : null;
            if (!btn) return;
            if (isTurnRequestInFlight()) return;

            const text = (btn.dataset.choiceText || btn.textContent || "").trim();
            if (!text) return;

            const ta = document.querySelector("#turn-form textarea[name=player_text]");
            if (!ta) return;
            ta.value = text;
            ta.dispatchEvent(new Event("input", { bubbles: true }));
            selectChoiceAction(btn);
            focusPlayerActionInput();
            showChoiceActionFeedback();
          });
        }

        function initActionJump() {
          document.body.addEventListener("click", function (evt) {
            const target = evt.target instanceof Element ? evt.target : null;
            const link = target ? target.closest("[data-action-jump]") : null;
            if (!link) return;
            evt.preventDefault();
            focusPlayerActionInput();
          });
        }

        function syncAdventurePanelTabs(root) {
          const scope = root || document;
          const tabs = Array.from(scope.querySelectorAll("[data-panel-tab]"));
          tabs.forEach((tab) => {
            const radio = document.getElementById(tab.dataset.panelTab || "");
            const checked = Boolean(radio && radio.checked);
            tab.setAttribute("aria-selected", checked ? "true" : "false");
            tab.setAttribute("tabindex", checked ? "0" : "-1");
            const panelId = tab.getAttribute("aria-controls");
            const panel = panelId ? document.getElementById(panelId) : null;
            if (panel) panel.hidden = !checked;
          });
        }

        function activateAdventurePanelTab(tab, shouldFocus) {
          if (!tab) return;
          const radio = document.getElementById(tab.dataset.panelTab || "");
          if (!radio) return;
          radio.checked = true;
          syncAdventurePanelTabs(tab.closest(".panel-tabs") || document);
          if (shouldFocus) {
            const targetTab = tab;
            targetTab.focus();
          }
        }

        function initAdventurePanelTabs() {
          document.querySelectorAll(".panel-tabs").forEach((root) => {
            const tabs = Array.from(root.querySelectorAll("[data-panel-tab]"));
            if (!tabs.length) return;
            syncAdventurePanelTabs(root);
            tabs.forEach((tab) => {
              tab.addEventListener("click", function () {
                activateAdventurePanelTab(tab, false);
              });
              tab.addEventListener("keydown", function (evt) {
                const currentIndex = tabs.indexOf(tab);
                let nextIndex = currentIndex;
                if (evt.key === "ArrowRight" || evt.key === "ArrowDown") nextIndex = (currentIndex + 1) % tabs.length;
                else if (evt.key === "ArrowLeft" || evt.key === "ArrowUp") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
                else if (evt.key === "Home") nextIndex = 0;
                else if (evt.key === "End") nextIndex = tabs.length - 1;
                else if (evt.key === "Enter" || evt.key === " ") {
                  evt.preventDefault();
                  activateAdventurePanelTab(tab, true);
                  return;
                } else {
                  return;
                }
                evt.preventDefault();
                activateAdventurePanelTab(tabs[nextIndex], true);
              });
            });
          });
        }

        function initRollContextActions() {
          document.body.addEventListener("click", function (evt) {
            const target = evt.target instanceof Element ? evt.target : null;
            const btn = target ? target.closest("[data-roll-context]") : null;
            if (!btn) return;
            if (isTurnRequestInFlight()) return;
            const context = (btn.dataset.rollContext || "").trim();
            if (!context) return;

            const stateBlock = document.querySelector("#turn-form textarea[name=state_block]");
            if (!stateBlock) return;
            const current = stateBlock.value.trim();
            const contextLines = current.split("\n").map((line) => line.trim()).filter(Boolean);
            if (contextLines.includes(context)) {
              showTurnContextFeedback("该线索已在本回合上下文中");
              revealTurnContextInput(stateBlock);

              const originalText = btn.textContent;
              btn.textContent = "已带入过";
              btn.disabled = true;
              window.setTimeout(function () {
                btn.textContent = originalText;
                btn.disabled = false;
              }, 1400);
              return;
            }
            stateBlock.value = current ? current + "\n" + context : context;
            stateBlock.dispatchEvent(new Event("input", { bubbles: true }));
            showTurnContextFeedback(context);
            revealTurnContextInput(stateBlock);

            const originalText = btn.textContent;
            btn.textContent = "已带入线索";
            btn.disabled = true;
            window.setTimeout(function () {
              btn.textContent = originalText;
              btn.disabled = false;
            }, 1400);
          });
        }

        function initTurnStreaming() {
          const form = document.getElementById("turn-form");
          if (!form || !window.fetch || !window.ReadableStream) return;

          form.addEventListener(
            "submit",
            async function (e) {
              e.preventDefault();
              e.stopImmediatePropagation();

              if (form.dataset.llmReady === "0") return;

              const chatHistory = document.getElementById("chat-history");
              if (!chatHistory) return;

              // Decide whether to follow scroll based on user's current position.
              lastTurnShouldFollowScroll = isNearBottom(chatHistory, 120);
              shouldFollowScroll = lastTurnShouldFollowScroll;
              hasUnreadNewContent = false;
              updateScrollButton();

              const ta = form.querySelector("textarea[name=player_text]");
              const playerText = ta && ta.value ? ta.value : "";
              if (!playerText.trim()) return;

              renderLatestChoices([]);
              const { turnEl, asstContent } = appendTurnSkeleton(chatHistory, playerText);
              if (shouldFollowScroll) scheduleAutoScroll();
              else updateScrollButton();

              setTurnRequestUI(true);
              currentTurnAbortController = new AbortController();
              let turnSucceeded = false;

              const fd = new FormData(form);
              try {
                const resp = await fetch("/game/turn/stream", {
                  method: "POST",
                  body: fd,
                  signal: currentTurnAbortController.signal,
                  headers: { Accept: "text/event-stream" },
                });
                if (!resp.ok || !resp.body) throw new Error(`HTTP ${resp.status}`);

                const reader = resp.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buf = "";

                while (true) {
                  const { value, done } = await reader.read();
                  if (done) break;
                  buf += decoder.decode(value, { stream: true });
                  const chunks = buf.split("\n\n");
                  buf = chunks.pop() || "";
                  for (const chunk of chunks) {
                    const lines = chunk.split("\n").filter(Boolean);
                    let event = "message";
                    let data = "";
                    for (const line of lines) {
                      if (line.startsWith("event:")) event = line.slice(6).trim();
                      if (line.startsWith("data:")) data += line.slice(5).trim();
                    }
                    if (!data) continue;
                    let payload;
                    try {
                      payload = JSON.parse(data);
                    } catch (_) {
                      payload = { message: data };
                    }

                    if (event === "delta") {
                      if (asstContent) {
                        if (asstContent.dataset.waiting === "1") {
                          asstContent.textContent = "";
                          asstContent.classList.remove("streaming-wait", "spinner");
                          delete asstContent.dataset.waiting;
                        }
                        asstContent.textContent += payload.text || "";
                      }
                      if (shouldFollowScroll) {
                        scheduleAutoScroll();
                      } else {
                        hasUnreadNewContent = true;
                        updateScrollButton();
                      }
                    } else if (event === "final") {
                      turnSucceeded = true;
                      renderFinalTurn(payload.turn, payload.recalled_world, payload.recalled_context, turnEl);
                      renderMarkdown(turnEl);
                      refreshCharacterPanel();
                      surfacePendingReview(payload.turn);
                      if (shouldFollowScroll) {
                        scheduleAutoScroll();
                      } else {
                        hasUnreadNewContent = true;
                        updateScrollButton();
                      }
                    } else if (event === "error") {
                      const asstMsg = turnEl.querySelector(".chat__msg--assistant");
                      if (asstMsg) {
                        asstMsg.innerHTML =
                          '<div class="chat__meta">DM</div>' +
                          '<div class="notice notice--err" role="status" aria-live="polite"><div class="notice__title">请求失败</div><div class="muted"></div></div>';
                        const m = asstMsg.querySelector(".notice .muted");
                        if (m) m.textContent = payload.message || "未知错误";
                      }
                      if (shouldFollowScroll) scheduleAutoScroll();
                      else updateScrollButton();
                    }
                  }
                }

                if (ta && turnSucceeded) {
                  ta.value = "";
                  resizeAutoGrowTextarea(ta);
                  clearSelectedChoiceActions();
                  clearTurnDraft(form);
                }
                const stateBlock = form.querySelector("textarea[name=state_block]");
                if (stateBlock && turnSucceeded) {
                  stateBlock.value = "";
                  clearStateBlockDraft(form);
                  hideTurnContextFeedback();
                }
                updateTurnSubmitState(form);
              } catch (err) {
                const aborted = err && err.name === "AbortError";
                if (aborted) {
                  renderTurnRequestNotice(turnEl, "请求已取消", "行动草稿已保留，可以修改后重新发送。", false);
                } else {
                  const message = err && err.message ? err.message : "网络连接中断，请稍后重试。";
                  renderTurnRequestNotice(turnEl, "请求失败", message, true);
                }
                if (shouldFollowScroll) {
                  scheduleAutoScroll();
                } else {
                  hasUnreadNewContent = true;
                  updateScrollButton();
                }
              } finally {
                currentTurnAbortController = null;
                setTurnRequestUI(false);
              }
            },
            true
          );
        }

        function submitTurnFormFromShortcut(form) {
          if (!form) return;
          updateTurnSubmitState(form);
          const submitBtn = form.querySelector("[data-turn-submit]");
          if (!submitBtn || submitBtn.disabled) return;
          form.requestSubmit(submitBtn);
        }

        function initTurnShortcuts() {
          const form = document.getElementById("turn-form");
          if (!form) return;
          const ta = form.querySelector("textarea[name=player_text]");
          if (!ta) return;
          ta.addEventListener("keydown", function (e) {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              submitTurnFormFromShortcut(form);
              return;
            }
            if (e.key === "Escape") {
              e.preventDefault();
              abortTurnRequest();
            }
          });
        }

        document.addEventListener("DOMContentLoaded", function () {
          renderMarkdown(document);
          initSkipLinks();
          scrollChatToBottom();
          initSidebarToggle();
          initGameLayoutResizer();
          initChatHistoryResizer();
          initAdvancedInputsToggle();
          initTurnDraftPersistence();
          initAutoGrowTextareas();
          initStateBlockDraftPersistence();
          initUnsavedTurnWarning();
          initTurnSubmitState();
          initQuickRollSubmitState();
          initLongSubmitForms();
          initConfirmForms();
          initTurnStreaming();
          initTurnShortcuts();
          initChoiceActions();
          initActionJump();
          initAdventurePanelTabs();
          initRollContextActions();

          // Scroll-follow button + scroll tracking (only on pages with chat-history).
          ensureScrollButton();
          const chat = document.getElementById("chat-history");
          if (chat) {
            updateScrollButton();
            chat.addEventListener("scroll", function () {
              const near = isNearBottom(chat, 120);
              if (near) {
                shouldFollowScroll = true;
                hasUnreadNewContent = false;
              } else {
                shouldFollowScroll = false;
              }
              updateScrollButton();
            });
          }

          const cancelBtn = document.getElementById("turn-cancel");
          if (cancelBtn) cancelBtn.addEventListener("click", abortTurnRequest);
        });
        document.body.addEventListener("htmx:afterSwap", function (evt) {
          renderMarkdown(evt.target);
          if (evt.target && evt.target.id === "character-panel") {
            syncPendingReviewCountFromPanel();
          }
          if (evt.target && evt.target.id === "chat-history") {
            if (lastTurnShouldFollowScroll) {
              scheduleAutoScroll();
            } else {
              hasUnreadNewContent = true;
              updateScrollButton();
            }
            const lastTurn = evt.target.lastElementChild;
            syncLatestChoicesFromTurn(lastTurn);
            if (lastTurn && lastTurn.dataset.turnHasPendingReview === "1") {
              surfacePendingReview({
                has_pending_review: true,
                pending_review_delta: Number(lastTurn.dataset.pendingReviewDelta || 1),
              });
            }
          }
        });

        document.body.addEventListener("htmx:beforeRequest", function (evt) {
          const elt = evt.detail && evt.detail.elt;
          if (elt && elt.querySelector("[data-quick-roll-submit]")) {
            setQuickRollRequestUI(elt, true);
            return;
          }
          if (!elt || elt.id !== "turn-form") return;
          if (elt.dataset.llmReady === "0") {
            evt.preventDefault();
            return;
          }
          setTurnRequestUI(true);
          const chat = document.getElementById("chat-history");
          lastTurnShouldFollowScroll = isNearBottom(chat, 120);
          shouldFollowScroll = lastTurnShouldFollowScroll;
          hasUnreadNewContent = false;
          updateScrollButton();
        });

        document.body.addEventListener("htmx:afterRequest", function (evt) {
          const elt = evt.detail && evt.detail.elt;
          if (elt && elt.querySelector("[data-quick-roll-submit]")) {
            setQuickRollRequestUI(elt, false);
            return;
          }
          if (!elt || elt.id !== "turn-form") return;
          if (evt.detail && evt.detail.successful === false) {
            setTurnRequestUI(false);
            return;
          }
          // Clear per-turn fields only after the turn is accepted; tags remain reusable.
          const ta = elt.querySelector("textarea[name=player_text]");
          if (ta) {
            ta.value = "";
            resizeAutoGrowTextarea(ta);
            clearSelectedChoiceActions();
          }
          const stateBlock = elt.querySelector("textarea[name=state_block]");
          if (stateBlock) stateBlock.value = "";
          clearTurnDraft(elt);
          clearStateBlockDraft(elt);
          hideTurnContextFeedback();
          setTurnRequestUI(false);
          updateTurnSubmitState(elt);
          refreshCharacterPanel();
        });
      })();
