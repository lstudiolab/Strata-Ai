const chat = document.querySelector('#chat');
const input = document.querySelector('#input');
const sendBtn = document.querySelector('#send');

function addMessage(role, text) {
  const row = document.createElement('div');
  row.className = 'msg';
  row.innerHTML = `<strong class="${role}">${role === 'user' ? 'You' : 'Strata'}:</strong> ${text}`;
  chat.appendChild(row);
  chat.scrollTop = chat.scrollHeight;
}

async function sendMessage() {
  const message = input.value.trim();
  if (!message) return;

  addMessage('user', message);
  input.value = '';

  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });

  if (!response.ok || !response.body) {
    addMessage('assistant', 'Something went wrong while contacting the AI server.');
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split('\n\n');
    buffer = events.pop() || '';

    for (const event of events) {
      if (!event.startsWith('data:')) continue;
      const raw = event.replace(/^data:\s*/, '').trim();
      if (!raw) continue;

      try {
        const payload = JSON.parse(raw);
        if (payload.type === 'status') {
          addMessage('assistant', payload.message);
        }
        if (payload.type === 'answer') {
          addMessage('assistant', payload.message);
        }
        if (payload.type === 'error') {
          addMessage('assistant', payload.message);
        }
      } catch (error) {
        console.error('Failed to parse SSE payload:', error);
      }
    }
  }
}

sendBtn.addEventListener('click', sendMessage);
input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') sendMessage();
});
