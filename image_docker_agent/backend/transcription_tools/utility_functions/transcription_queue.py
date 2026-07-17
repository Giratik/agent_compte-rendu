#backend/transcription_tools/utility_functions/transcription_queue.py

import asyncio
from collections import deque
from typing import Dict, Optional, Tuple
import uuid
import time

class TranscriptionQueue:
    def __init__(self):
        self.queue = deque()
        self.current_user: Optional[str] = None
        self.current_user_token: Optional[str] = None  # Store the token of the current user
        self.lock = asyncio.Lock()
        self.condition = asyncio.Condition(self.lock)
        
        # --- NOUVEAU : Système de Heartbeat ---
        self.last_seen: Dict[str, float] = {}
        self.TIMEOUT_SECONDS = 20  # Expulsion si aucune nouvelle pendant 20s

    def _cleanup_stale_tokens(self):
        """Nettoie paresseusement les requêtes fantômes de la file."""
        current_time = time.time()
        active_queue = deque()
        for user_id, token in self.queue:
            # Si le token a été vu récemment (ou vient d'être créé)
            if current_time - self.last_seen.get(token, current_time) <= self.TIMEOUT_SECONDS:
                active_queue.append((user_id, token))
            else:
                # Le token est expiré, on l'oublie
                if token in self.last_seen:
                    del self.last_seen[token]
        self.queue = active_queue

    async def add_to_queue(self, user_id: str) -> Tuple[int, str]:
        async with self.lock:
            self._cleanup_stale_tokens()
            queue_token = str(uuid.uuid4())
            self.queue.append((user_id, queue_token))
            
            # Initialisation du heartbeat
            self.last_seen[queue_token] = time.time()
            
            # La position doit inclure le slot actuellement occupé
            position = len(self.queue) + (1 if self.current_user is not None else 0)
            return position, queue_token

    async def get_queue_position(self, queue_token: str) -> Optional[int]:
        async with self.lock:
            # Mise à jour du heartbeat à chaque fois que le frontend prend des nouvelles
            if queue_token in self.last_seen or any(t == queue_token for _, t in self.queue):
                self.last_seen[queue_token] = time.time()
                
            self._cleanup_stale_tokens()

            # First check if this token belongs to the current user
            if self.current_user is not None and self.current_user_token == queue_token:
                return 1

            # Check if token is in queue
            for i, (user_id, token) in enumerate(self.queue):
                if token == queue_token:
                    offset = 1 if self.current_user is not None else 0
                    return i + 1 + offset

            # Token not found anywhere (soit terminé, soit expulsé)
            return None

    async def acquire_transcription_slot(self, queue_token: str) -> bool:
        """Try to acquire transcription slot, return True if acquired, False if not found in queue"""
        async with self.lock:
            if queue_token in self.last_seen:
                self.last_seen[queue_token] = time.time()
                
            self._cleanup_stale_tokens()

            # Check if there's already a current user (slot is taken)
            if self.current_user is not None:
                return False

            # Check if this token is at the front of the queue
            if len(self.queue) > 0 and self.queue[0][1] == queue_token:
                # Remove from queue and set as current user
                self.current_user, user_token = self.queue.popleft()
                self.current_user_token = user_token  # Store the token too
                return True
            return False

    async def release_transcription_slot(self):
        """Release the current transcription slot"""
        async with self.lock:
            # Nettoyage du dictionnaire heartbeat pour ce token
            if self.current_user_token in self.last_seen:
                del self.last_seen[self.current_user_token]
                
            self.current_user = None
            self.current_user_token = None
            self._cleanup_stale_tokens()

    async def get_current_queue_info(self) -> Dict:
        """Get current queue information"""
        async with self.lock:
            self._cleanup_stale_tokens()
            return {
                "current_user": self.current_user,
                "queue_length": len(self.queue),
                "is_busy": self.current_user is not None
            }

    async def is_current_token(self, queue_token: str) -> bool:
        async with self.lock:
            # CORRECTION : On compare bien au token, pas au user_id
            return self.current_user_token == queue_token 
    
# Global queue instance
transcription_queue = TranscriptionQueue()