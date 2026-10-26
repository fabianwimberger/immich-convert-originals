/** Live progress feed. Auto-reconnects; fans out messages to listeners. */
class WebSocketClient {
  constructor() {
    this.listeners = [];
    this.reconnectListeners = [];
    this.socket = null;
    this._everConnected = false;
    this._connect();
  }

  _connect() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    this.socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
    this.socket.addEventListener("open", () => {
      if (this._everConnected) {
        this.reconnectListeners.forEach((cb) => {
          try {
            cb();
          } catch (err) {
            console.error(err);
          }
        });
      }
      this._everConnected = true;
    });
    this.socket.addEventListener("message", (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (err) {
        return;
      }
      // One bad listener must not starve the rest.
      this.listeners.forEach((cb) => {
        try {
          cb(data);
        } catch (err) {
          console.error(err);
        }
      });
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

  onReconnect(callback) {
    this.reconnectListeners.push(callback);
    return () => {
      this.reconnectListeners = this.reconnectListeners.filter((cb) => cb !== callback);
    };
  }
}

const wsClient = new WebSocketClient();
