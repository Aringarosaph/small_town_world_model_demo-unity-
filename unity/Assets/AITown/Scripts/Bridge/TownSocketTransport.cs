using System;
using System.IO;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace STWM.AITown.Bridge
{
    public interface ITownSocketTransport : IDisposable
    {
        WebSocketState State { get; }
        Task ConnectAsync(Uri endpoint, TimeSpan keepAliveInterval, CancellationToken cancellationToken);
        Task SendTextAsync(string text, CancellationToken cancellationToken);
        Task<string> ReceiveTextAsync(CancellationToken cancellationToken);
        Task CloseAsync(CancellationToken cancellationToken);
    }

    public sealed class ClientWebSocketTransport : ITownSocketTransport
    {
        private const int ReceiveBufferSize = 8192;
        private const int MaximumMessageBytes = 1024 * 1024;
        private ClientWebSocket socket;

        public WebSocketState State => socket?.State ?? WebSocketState.None;

        public async Task ConnectAsync(Uri endpoint, TimeSpan keepAliveInterval, CancellationToken cancellationToken)
        {
            DisposeSocket();
            socket = new ClientWebSocket();
            socket.Options.KeepAliveInterval = keepAliveInterval;
            await socket.ConnectAsync(endpoint, cancellationToken).ConfigureAwait(false);
        }

        public async Task SendTextAsync(string text, CancellationToken cancellationToken)
        {
            if (socket == null || socket.State != WebSocketState.Open)
            {
                throw new InvalidOperationException("WebSocket is not open.");
            }

            var bytes = Encoding.UTF8.GetBytes(text);
            await socket.SendAsync(
                    new ArraySegment<byte>(bytes),
                    WebSocketMessageType.Text,
                    true,
                    cancellationToken)
                .ConfigureAwait(false);
        }

        public async Task<string> ReceiveTextAsync(CancellationToken cancellationToken)
        {
            if (socket == null)
            {
                throw new InvalidOperationException("WebSocket is not initialized.");
            }

            var buffer = new byte[ReceiveBufferSize];
            using (var stream = new MemoryStream())
            {
                while (true)
                {
                    var result = await socket.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken)
                        .ConfigureAwait(false);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        return null;
                    }

                    if (result.MessageType != WebSocketMessageType.Text)
                    {
                        throw new InvalidDataException($"Unsupported WebSocket message type: {result.MessageType}");
                    }

                    stream.Write(buffer, 0, result.Count);
                    if (stream.Length > MaximumMessageBytes)
                    {
                        throw new InvalidDataException($"WebSocket message exceeded {MaximumMessageBytes} bytes.");
                    }

                    if (result.EndOfMessage)
                    {
                        return Encoding.UTF8.GetString(stream.ToArray());
                    }
                }
            }
        }

        public async Task CloseAsync(CancellationToken cancellationToken)
        {
            if (socket == null)
            {
                return;
            }

            if (socket.State == WebSocketState.Open || socket.State == WebSocketState.CloseReceived)
            {
                await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Unity client closing", cancellationToken)
                    .ConfigureAwait(false);
            }
        }

        public void Dispose()
        {
            DisposeSocket();
        }

        private void DisposeSocket()
        {
            socket?.Dispose();
            socket = null;
        }
    }
}
