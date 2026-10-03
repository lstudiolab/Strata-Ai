<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Strata AI</title>
    <style>
      body {
        font-family: Arial, sans-serif;
        margin: 0;
        background: #0f172a;
        color: #e2e8f0;
      }
      .container {
        max-width: 900px;
        margin: 40px auto;
        padding: 20px;
      }
      h1 {
        margin-bottom: 20px;
      }
      #chat {
        background: #111827;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        min-height: 320px;
        max-height: 500px;
        overflow-y: auto;
        margin-bottom: 16px;
      }
      .msg {
        margin-bottom: 14px;
        line-height: 1.5;
      }
      .user {
        color: #93c5fd;
      }
      .assistant {
        color: #86efac;
      }
      .input-row {
        display: flex;
        gap: 12px;
      }
      input {
        flex: 1;
        padding: 12px 14px;
        border-radius: 10px;
        border: 1px solid #475569;
        background: #0f172a;
        color: #f8fafc;
      }
      button {
        padding: 12px 20px;
        border: none;
        border-radius: 10px;
        background: #2563eb;
        color: white;
        cursor: pointer;
      }
    </style>
  </head>
  <body>
    <div class="container">
      <h1>Strata AI</h1>
      <div id="chat"></div>
      <div class="input-row">
        <input id="input" type="text" placeholder="Ask Strata anything..." />
        <button id="send">Send</button>
      </div>
    </div>

    <script src="/static/app.js"></script>
  </body>
</html>
