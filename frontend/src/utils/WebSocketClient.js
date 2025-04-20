import { ref } from 'vue';

/**
 * WebSocket客户端类
 * 
 * 用于处理与WebSocket服务器的连接和通信
 * 
 * @class WebSocketClient
 */
class WebSocketClient {
  /**
   * 创建一个WebSocket客户端实例
   * 
   * @param {string} url - WebSocket服务器URL
   * @param {Object} options - 配置选项
   */
  constructor(url, options = {}) {
    this.url = url;
    this.options = options;
    this.socket = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = options.maxReconnectAttempts || 5;
    this.reconnectInterval = options.reconnectInterval || 3000;
    this.messageHandlers = new Map();
    this.connectionStatus = ref('disconnected'); // 响应式连接状态
    this.lastError = ref(null);
  }

  /**
   * 建立WebSocket连接
   */
  connect() {
    this.connectionStatus.value = 'connecting';
    console.log(`正在连接WebSocket: ${this.url}`);
    
    try {
      this.socket = new WebSocket(this.url);
      
      this.socket.onopen = () => {
        console.log('WebSocket连接已建立');
        this.reconnectAttempts = 0;
        this.connectionStatus.value = 'connected';
        this.lastError.value = null;
        
        if (this.options.onOpen) {
          this.options.onOpen();
        }
      };
      
      this.socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('收到WebSocket消息:', message);
          
          // 处理消息类型
          if (message.type && this.messageHandlers.has(message.type)) {
            this.messageHandlers.get(message.type)(message);
          }
          
          if (this.options.onMessage) {
            this.options.onMessage(message);
          }
        } catch (error) {
          console.error('解析WebSocket消息失败:', error);
        }
      };
      
      this.socket.onclose = (event) => {
        this.connectionStatus.value = 'disconnected';
        console.log(`WebSocket连接已关闭，代码: ${event.code}, 理由: ${event.reason}`);
        
        if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
          console.log(`尝试重新连接 (${this.reconnectAttempts + 1}/${this.maxReconnectAttempts})...`);
          this.reconnectAttempts++;
          setTimeout(() => this.connect(), this.reconnectInterval);
        }
        
        if (this.options.onClose) {
          this.options.onClose(event);
        }
      };
      
      this.socket.onerror = (error) => {
        console.error('WebSocket错误:', error);
        this.lastError.value = '连接失败，请检查网络或服务器状态';
        
        if (this.options.onError) {
          this.options.onError(error);
        }
      };
    } catch (error) {
      console.error('创建WebSocket连接失败:', error);
      this.connectionStatus.value = 'error';
      this.lastError.value = '创建连接失败: ' + error.message;
    }
  }

  /**
   * 断开WebSocket连接
   */
  disconnect() {
    if (this.socket) {
      this.socket.close();
      this.socket = null;
      this.connectionStatus.value = 'disconnected';
    }
  }

  /**
   * 发送消息到服务器
   * 
   * @param {string} type - 消息类型
   * @param {Object} data - 消息数据
   * @returns {boolean} 是否发送成功
   */
  send(type, data = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      console.error('WebSocket未连接，无法发送消息');
      return false;
    }

    try {
      const message = JSON.stringify({
        type,
        ...data
      });
      
      this.socket.send(message);
      return true;
    } catch (error) {
      console.error('发送WebSocket消息失败:', error);
      return false;
    }
  }

  /**
   * 注册消息处理器
   * 
   * @param {string} messageType - 消息类型
   * @param {Function} handler - 处理函数
   */
  onMessage(messageType, handler) {
    this.messageHandlers.set(messageType, handler);
  }

  /**
   * 移除消息处理器
   * 
   * @param {string} messageType - 消息类型
   */
  offMessage(messageType) {
    this.messageHandlers.delete(messageType);
  }
}

export default WebSocketClient; 