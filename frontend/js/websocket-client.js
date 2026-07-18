/** Live progress feed. Auto-reconnects; fans out messages to listeners. */
class WebSocketClient {
  constructor() {
    this.listeners = [];
    this.socket = null;
    this._connect();
  }

  _connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    this.socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      this.listeners.forEach((cb) => cb(data));
    });
    this.socket.addEventListener("close", () => {
      setTimeout(() => this._connect(), 2000);
    });
  }

  onMessage(callback) {
    this.listeners.push(callback);
    return () => {
      this.listeners = this.listeners.filter((cb) => cb !== callback);
    };
  }
}

const wsClient = new WebSocketClient();
