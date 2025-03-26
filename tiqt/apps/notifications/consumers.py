import json
from channels.generic.websocket import AsyncWebsocketConsumer

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()

    async def receive(self, text_data):
        await self.send(text_data=json.dumps({"message": "Notificação recebida"}))

    async def disconnect(self, close_code):
        pass
