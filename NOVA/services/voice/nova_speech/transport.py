"""WebSocket transport — Local daemon for Node.js client communication.

Binds 127.0.0.1 ONLY. Protocol:
  Client -> Server: {"type": "transcript", "text": "..."}
  Client -> Server: {"type": "wake"}
  Client -> Server: {"type": "command", "skill": "generate_news"}
  Server -> Client: {"type": "speaking", "text": "...", "emotion": "..."}
  Server -> Client: {"type": "status", "state": "listening|thinking|speaking"}
  Server -> Client: {"type": "broadcast_progress", "stage": 1, ...}
"""

import asyncio
import json
import logging

import websockets

logger = logging.getLogger("nova.transport")


class NovaTransport:
    """WebSocket daemon for inter-process communication."""

    def __init__(self, config: dict, orchestrator):
        self._host = config["transport"]["host"]
        self._port = config["transport"]["port"]
        self._orch = orchestrator
        self._clients: set = set()

    async def start(self):
        """Start WebSocket server on localhost only."""
        server = await websockets.serve(
            self._handle_client,
            self._host,
            self._port,
        )
        logger.info("nova-transport: WebSocket listening on ws://%s:%d", self._host, self._port)
        await server.wait_closed()

    async def _handle_client(self, websocket):
        """Handle a single WebSocket client connection."""
        self._clients.add(websocket)
        logger.info("nova-transport: client connected (%d total)", len(self._clients))
        try:
            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "transcript":
                    # Manual transcript injection (from Node client)
                    text = data.get("text", "")
                    self._orch._handle_transcript(text)
                elif msg_type == "wake":
                    # Simulate wake word from external trigger
                    self._orch._handle_transcript("")
                elif msg_type == "command":
                    # Direct skill invocation
                    skill = data.get("skill", "")
                    if skill:
                        await self._orch._skills.execute(skill, data.get("text", ""))
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("nova-transport: client disconnected (%d remaining)", len(self._clients))

    async def broadcast(self, event: dict):
        """Send event to all connected clients."""
        if not self._clients:
            return
        message = json.dumps(event)
        await asyncio.gather(
            *(client.send(message) for client in self._clients),
            return_exceptions=True,
        )
