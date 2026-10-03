// Polls the message thread every 3s for new messages -- no websockets, a
// deliberate, documented limitation carried over from the original
// monolith's design (fine for a practice app's traffic).
document.addEventListener("DOMContentLoaded", () => {
  const thread = document.getElementById("message-thread");
  if (!thread) return;

  const otherUsername = thread.dataset.other;
  let latestId = thread.dataset.latest;

  async function poll() {
    try {
      const resp = await fetch(`/messages/${encodeURIComponent(otherUsername)}/poll?since=${encodeURIComponent(latestId)}`);
      if (!resp.ok) return;
      const messages = await resp.json();
      for (const m of messages) {
        const bubble = document.createElement("div");
        bubble.className = "message-bubble " + (m.sender === window.CURRENT_USERNAME ? "mine" : "theirs");
        bubble.innerHTML = `${escapeHtml(m.content)}<div class="message-time">${escapeHtml(m.sent_at)}</div>`;
        thread.appendChild(bubble);
        latestId = m.sent_at_id;
      }
      if (messages.length) thread.scrollTop = thread.scrollHeight;
    } catch (e) {
      // A transient poll failure isn't worth surfacing to the user.
    }
  }

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s;
    return div.innerHTML;
  }

  thread.scrollTop = thread.scrollHeight;
  setInterval(poll, 3000);
});
