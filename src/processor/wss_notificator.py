from collections import defaultdict

from starlette.websockets import WebSocket, WebSocketDisconnect


class WSSNotificator:
    def __init__(self):
        self.wss_connections_map = defaultdict(list)

    def register_wss_connection(self, monitor_id: str, wss_connection: WebSocket):
        self.wss_connections_map[monitor_id].append(wss_connection)

    def unregister_wss_connection(self, monitor_id: str, wss_connection: WebSocket):
        self.wss_connections_map[monitor_id].remove(wss_connection)

    async def send_wss_notification(self, message: dict):
        monitor_id = message.get("monitor_id")
        if monitor_id in self.wss_connections_map:
            for wss_connection in list(self.wss_connections_map[monitor_id]):
                try:
                    await wss_connection.send_text(message.get("msg"))
                except WebSocketDisconnect:
                    self.wss_connections_map[monitor_id].remove(wss_connection)

