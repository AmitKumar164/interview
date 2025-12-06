import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.utils import timezone 
from .models import *
User = get_user_model()
from user_data.models import UserProfile
# from session_app.models import OnetoOneUserCount, Session
from django.core.cache import cache
from asgiref.sync import sync_to_async

# # live_users = set()
# # matchmaking_queue = []
# # mentor_user = set()
# # mentee_user = set()
# MAX_CONNECTIONS_PER_PAIR = 1  # X times

# @sync_to_async
# def cache_get(key, default=None):
#     return cache.get(key, default)

# @sync_to_async
# def cache_set(key, value, timeout=None):
#     cache.set(key, value, timeout)

# @sync_to_async
# def cache_delete(key):
#     cache.delete(key)

# @sync_to_async
# def get_user_interests(user):
#     try:
#         profile = user.profile
#     except UserProfile.DoesNotExist:
#         return set()
#     return set(profile.tags.values_list("name", flat=True))


# class ConnectifyConsumer(AsyncWebsocketConsumer):
#     matchmaking_queue = []
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.user = None
#         self.peer = None
#         self.room_group_name = None

#     async def connect(self):
#         close_old_connections()

#         self.session_id = self.scope["url_route"]["kwargs"].get("session_id")
#         username = self.scope["url_route"]["kwargs"].get("username")
#         print(f"Session ID: {self.session_id}, Username: {username}")
#         if not username:
#             await self.close(code=4003)
#             return

#         self.user = await self.get_user_by_username(username)
#         if not self.user:
#             await self.close(code=4003)
#             return

#         await self.accept()
#         self.room_group_name = f"user_{self.user.username}"

#         await self.channel_layer.group_add(
#             self.room_group_name,
#             self.channel_name
#         )
#         users = await cache_get(f'{self.session_id}_live_users', set())
#         users.add(self.user.username)
#         await cache_set(f'{self.session_id}_live_users', users, timeout=36000)

#         mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#         mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())
#         user_type = await self.get_user_type(self.user)
#         if user_type in ['Mentor', 'Admin']:
#             mentor_user.add(self.user.username)
#             await cache_set(f'{self.session_id}_mentor_user', mentor_user, timeout=36000)
#         else:
#             mentee_user.add(self.user.username)
#             await cache_set(f'{self.session_id}_mentee_user', mentee_user, timeout=36000)

#         print(f"[CONNECTED] {self.user.username}")

#     @database_sync_to_async
#     def get_user_by_username(self, username):
#         try:
#             return User.objects.get(username=username)
#         except User.DoesNotExist:
#             return None

#     @database_sync_to_async
#     def get_user_type(self, user):
#         try:
#             return user.profile.user_type
#         except UserProfile.DoesNotExist:
#             return 'Mentee'

#     async def disconnect(self, close_code):
#         live_users = await cache_get(f'{self.session_id}_live_users', set())
#         if self.user and self.user.username in live_users:
#             live_users.remove(self.user.username)
#             await cache_set(f'{self.session_id}_live_users', live_users, timeout=36000)
#             mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#             mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())

#             mentor_user.discard(self.user.username)
#             mentee_user.discard(self.user.username)
#             await cache_set(f'{self.session_id}_mentor_user', mentor_user, timeout=36000)
#             await cache_set(f'{self.session_id}_mentee_user', mentee_user, timeout=36000)

#         if self.room_group_name:
#             await self.channel_layer.group_discard(
#                 self.room_group_name,
#                 self.channel_name
#             )

#         if self.peer:
#             await self.channel_layer.send(
#                 self.peer,
#                 {
#                     "type": "disconnect",
#                     "text": json.dumps({
#                         "channel": "disconnect",
#                         "data": {"username": self.user.username}
#                     })
#                 }
#             )
#             self.peer = None
#         print(f"[DISCONNECTED] {self.user.username}")

#     async def receive(self, text_data):
#         try:
#             data = json.loads(text_data)
#             channel = data.get("channel")
#             print(f"[RECEIVE] {self.user.username}: {channel}")
#             message_data = data.get("data", {})

#             if channel == "match":
#                 await self.handle_match(message_data)

#             elif channel == "message":
#                 await self.handle_message(message_data)

#             elif channel == "typing":
#                 await self.handle_typing(message_data)

#             elif channel == "webrtc":
#                 await self.handle_webrtc(message_data)

#             elif channel == "join_room":
#                 await self.handle_join_room(message_data)

#             elif channel == "leave_room":
#                 await self.handle_leave_room()

#             elif channel == "media-state-change":
#                 await self.handle_media_state_change(message_data)

#             elif channel == "live-users":
#                 await self.send(text_data=json.dumps({
#                     "channel": "live-users",
#                     "data": len(await cache_get(f'{self.session_id}_live_users', set()))
#                 }))
#             elif channel == "offer":
#                 print("Received WebRTC offer")
#                 await self.offer(message_data)
#                 print("Offer forwarded to peer")
            
#             elif channel == "answer":
#                 print("Received WebRTC answer")
#                 await self.answer(message_data)
#                 print("Answer forwarded to peer")
            
#             elif channel == "ice-candidate":
#                 print("Received WebRTC ice-candidate")
#                 await self.ice_candidate(message_data)
#                 print("Ice-candidate forwarded to peer")
            
#             elif channel == "disconnect":
#                 mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#                 mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())
#                 session = await database_sync_to_async(Session.objects.get)(id=self.session_id)
#                 entry = await database_sync_to_async(
#                     lambda: OnetoOneUserCount.objects
#                     .filter(session=session)
#                     .filter(models.Q(user1=self.user) | models.Q(user2=self.user))
#                     .order_by('-start_date')
#                     .first()
#                 )()
#                 if entry and entry.end_date is None:
#                     entry.end_date = timezone.now()
#                     await database_sync_to_async(entry.save)()
                
#                     self_user_type = await self.get_user_type(self.user)
#                     if self_user_type in ["Admin", "Mentor"]:
#                         mentor_user.add(self.user.username)
#                         await cache_set(f'{self.session_id}_mentor_user', mentor_user, timeout=36000)
#                         print(f"[DISCONNECT] {self.user.username} re-added to mentor_user")
#                     else:
#                         mentee_user.add(self.user.username)
#                         await cache_set(f'{self.session_id}_mentee_user', mentee_user, timeout=36000)
#                         print(f"[DISCONNECT] {self.user.username} re-added to mentee_user")

#                     # Re-add peer (if exists)
#                     if self.peer:
#                         print(f"[DISCONNECT] Notifying peer via channel: {self.peer}")
#                         await self.channel_layer.send(
#                             self.peer,
#                             {
#                                 "type": "readd.user",  # Triggers method `readd_user`
#                                 "text": json.dumps({
#                                     "from": self.user.username
#                                 })
#                             }
#                         )
#                 await self.disconnect(message_data)


#         except json.JSONDecodeError:
#             await self.send(text_data=json.dumps({
#                 "error": "Invalid JSON format"
#             }))
#         except Exception as e:
#             print(f"[ERROR] {str(e)}")
#             await self.send(text_data=json.dumps({
#                 "error": "An internal error occurred"
#             }))

#     async def handle_match(self, data):
#         print("###############################")
#         mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#         mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())
#         print(mentor_user)
#         print(mentee_user)
#         print("###############################")

#         # interests = {"python", "web", "ai"}  # Replace with dynamic interests if needed
#         interests = await get_user_interests(self.user)
#         print(f"Interests: {interests}")
#         current_user = {
#             "id": self.user.id,
#             "name": f"{self.user.first_name} {self.user.last_name}",
#             "interests": list(interests),
#             "experience": self.user.profile.user_experience,
#             "domain": self.user.profile.domain
#         }

#         is_mentor = self.user.username in mentor_user
#         is_mentee = self.user.username in mentee_user

#         for peer_consumer, peer_interests in list(self.matchmaking_queue):
#             if peer_consumer == self:
#                 continue

#             peer_is_mentor = peer_consumer.user.username in mentor_user
#             peer_is_mentee = peer_consumer.user.username in mentee_user

#             if (is_mentor and peer_is_mentee) or (is_mentee and peer_is_mentor):
#                 common_interests = interests.intersection(peer_interests)
#                 if common_interests:
#                     # ✅ Check connection limit in DB
#                     from asgiref.sync import sync_to_async
#                     connection_count = await sync_to_async(
#                         lambda: OnetoOneUserCount.objects.filter(
#                             session_id=self.session_id,
#                             user1=self.user if is_mentor else peer_consumer.user,
#                             user2=self.user if is_mentee else peer_consumer.user
#                         ).count()
#                     )()

#                     if connection_count >= MAX_CONNECTIONS_PER_PAIR:
#                         print(f"❌ Pair {self.user.username} & {peer_consumer.user.username} already connected {connection_count} times. Skipping.")
#                         continue  # Skip this peer

#                     # ✅ Proceed with match
#                     self.matchmaking_queue.remove((peer_consumer, peer_interests))

#                     peer_user = {
#                         "id": peer_consumer.user.id,
#                         "name": f"{peer_consumer.user.first_name} {peer_consumer.user.last_name}",
#                         "interests": list(common_interests),
#                         "experience": peer_consumer.user.profile.user_experience,
#                         "domain": peer_consumer.user.profile.domain
#                     }

#                     self.peer = peer_consumer.channel_name
#                     peer_consumer.peer = self.channel_name

#                     # Save match to DB
#                     await self.save_match(self.user, peer_consumer.user, self.session_id)

#                     # Remove from sets
#                     mentor_user.discard(self.user.username)
#                     mentor_user.discard(peer_consumer.user.username)
#                     mentee_user.discard(self.user.username)
#                     mentee_user.discard(peer_consumer.user.username)
#                     await cache_set(f'{self.session_id}_mentor_user', mentor_user, timeout=36000)
#                     await cache_set(f'{self.session_id}_mentee_user', mentee_user, timeout=36000)

#                     # Notify both
#                     await self.send(text_data=json.dumps({
#                         "channel": "connected",
#                         "data": peer_user,
#                     }))
#                     await peer_consumer.send(text_data=json.dumps({
#                         "channel": "connected",
#                         "data": current_user,
#                     }))
#                     await self.send(text_data=json.dumps({
#                         "channel": "begin",
#                         "data": list(common_interests)
#                     }))
#                     print("✅ Peer connected")
#                     return

#         self.matchmaking_queue.append((self, interests))
#         await self.send(text_data=json.dumps({
#             "channel": "waiting",
#             "message": "Waiting for a match..."
#         }))

#     async def handle_message(self, data):
#         if not self.peer:
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "message",
#                 "text": json.dumps({
#                     "channel": "message",
#                     "data": data,
#                     "from": self.user.username
#                 })
#             }
#         )

#     async def handle_typing(self, data):
#         if not self.peer:
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "typing",
#                 "text": json.dumps({
#                     "channel": "typing",
#                     "data": data,
#                     "from": self.user.username
#                 })
#             }
#         )

#     async def handle_webrtc(self, data):
#         if not self.peer:
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "webrtc",
#                 "text": json.dumps({
#                     "channel": "webrtc",
#                     "data": data,
#                     "from": self.user.username
#                 })
#             }
#         )

#     async def handle_join_room(self, data):
#         self.peer = data.get("peer_channel_name")
#         print(f"{self.user.username} joined room with peer {self.peer}")

#     async def handle_leave_room(self):
#         print(f"{self.user.username} left the room")
#         self.peer = None

#     async def handle_media_state_change(self, data):
#         if not self.peer:
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "media_state_change",
#                 "text": json.dumps({
#                     "channel": "media-state-change",
#                     "data": data,
#                     "from": self.user.username
#                 })
#             }
#         )
#     async def media_state_change(self, event):
#         await self.send(text_data=event["text"])
    
#     # Method to send offer to peer (called when message received from WebSocket)
#     async def offer(self, data):
#         if not self.peer:
#             print("[OFFER] No peer connected")
#             return

#         await self.channel_layer.send(
#             self.peer,  # peer is a channel_name string
#             {
#                 "type": "receive.offer",  # <- Must match the method name below, but with dot
#                 "text": json.dumps({
#                     "channel": "offer",
#                     "data": data,
#                     "from": self.user.username,
#                 }),
#             },
#         )

#     # Method to handle message received from channel layer
#     async def receive_offer(self, event):
#         await self.send(text_data=event["text"])

#     # Method to send offer to peer (called when message received from WebSocket)
#     async def answer(self, data):
#         if not self.peer:
#             print("[OFFER] No peer connected")
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "receive.answer",
#                 "text": json.dumps({
#                     "channel": "answer",
#                     "data": data,
#                     "from": self.user.username,
#                 }),
#             },
#         )

#     # Method to handle message received from channel layer
#     async def receive_answer(self, event):
#         await self.send(text_data=event["text"])

#     async def ice_candidate(self, data):
#         if not self.peer:
#             print("[OFFER] No peer connected")
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "receive.ice_candidate",
#                 "text": json.dumps({
#                     "channel": "ice-candidate",
#                     "data": data,
#                     "from": self.user.username,
#                 }),
#             },
#         )

#     async def receive_ice_candidate(self, event):
#         await self.send(text_data=event["text"])

#     async def disconnect(self, data):
#         if not self.peer:
#             print("[OFFER] No peer connected")
#             return

#         await self.channel_layer.send(
#             self.peer,
#             {
#                 "type": "receive.disconnect",
#                 "text": json.dumps({
#                     "channel": "disconnect",
#                     "data": data,
#                     "from": self.user.username,
#                 }),
#             },
#         )

#     async def receive_disconnect(self, event):
#         await self.send(text_data=event["text"])

#     # @database_sync_to_async
#     # def save_match_to_count_model(self, user_a, user_b, session_id):
#     #     mentor_user = cache_get(f'{self.session_id}_mentor_user', set())
#     #     mentee_user = cache_get(f'{self.session_id}_mentee_user', set())
#     #     mentor = user_a if user_a.username in mentor_user else user_b
#     #     mentee = user_b if user_a.username in mentee_user else user_a

#     #     obj = OnetoOneUserCount.objects.create(
#     #         session_id=session_id,
#     #         user1=mentor,
#     #         user2=mentee,
#     #         duration= 0.0,
#     #         start_date= timezone.now(),
#     #         end_date= None,
#     #     )
#     async def save_match(self, user_a, user_b, session_id):
#         mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#         mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())
#         await self._save_match_to_count_model(user_a, user_b, session_id, mentor_user, mentee_user)

#     @database_sync_to_async
#     def _save_match_to_count_model(self, user_a, user_b, session_id, mentor_user, mentee_user):
#         mentor = user_a if user_a.username in mentor_user else user_b
#         mentee = user_b if user_b.username in mentee_user else user_a
#         OnetoOneUserCount.objects.create(
#             session_id=session_id,
#             user1=mentor,
#             user2=mentee,
#             duration=0.0,
#             start_date=timezone.now(),
#             end_date=None,
#         )


#     async def readd_user(self, event):
#         user_type = await self.get_user_type(self.user)
#         mentor_user = await cache_get(f'{self.session_id}_mentor_user', set())
#         mentee_user = await cache_get(f'{self.session_id}_mentee_user', set())
#         if user_type in ["Admin", "Mentor"]:
#             mentor_user.add(self.user.username)
#             await cache_set(f'{self.session_id}_mentor_user', mentor_user, timeout=36000)
#             print(f"[RE-ADD] {self.user.username} added back to mentor_user")
#         else:
#             mentee_user.add(self.user.username)
#             await cache_set(f'{self.session_id}_mentee_user', mentee_user, timeout=36000)
#             print(f"[RE-ADD] {self.user.username} added back to mentee_user")

import json
import logging
from typing import Optional, Dict, List

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from django.db import close_old_connections
from django.contrib.auth import get_user_model
from channels.db import database_sync_to_async
from user_data.models import UserProfile

User = get_user_model()
logger = logging.getLogger("connectify")

def mapping_cache_key(session_id: str) -> str:
    return f"event_{session_id}_connect_mapping"

def online_users_cache_key(session_id: str) -> str:
    return f"event_{session_id}_online_users"

class ConnectifyConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        print("\n\n========== CONNECT STARTED ==========")
        close_old_connections()

        self.session_id = self.scope["url_route"]["kwargs"].get("session_id")
        username = self.scope["url_route"]["kwargs"].get("username")

        print(f"[CONNECT] SESSION = {self.session_id}")
        print(f"[CONNECT] USERNAME = {username}")

        if not username or not self.session_id:
            print("[CONNECT ERROR] Missing username or session_id")
            await self.close(code=4003)
            return

        if not getattr(self, "channel_layer", None):
            print("[CONNECT ERROR] channel_layer missing")
            await self.close(code=1011)
            return

        # Fetch user
        try:
            print(f"[CONNECT] Fetching user record for {username}")
            self.user = await database_sync_to_async(User.objects.get)(username=username)
        except User.DoesNotExist:
            print(f"[CONNECT ERROR] User does not exist: {username}")
            await self.close(code=4003)
            return

        # Fetch profile
        try:
            print(f"[CONNECT] Fetching user profile for {username}")
            profile = await database_sync_to_async(UserProfile.objects.get)(user=self.user)
        except UserProfile.DoesNotExist:
            print(f"[CONNECT ERROR] Profile not found for user: {username}")
            await self.close(code=4003)
            return

        self.profile_type = profile.user_type
        self.room_group_name = None

        print(f"[CONNECT] Profile Type = {self.profile_type}")
        await self.accept()
        print(f"[WS ACCEPTED] {self.user.username}")

        # If interviewer
        if self.profile_type == "Interviewer":
            self.room_group_name = f"room_{self.user.username}_{self.session_id}"
            print(f"[INTERVIEWER ROOM CREATED] {self.room_group_name}")
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        # If interviewee
        elif self.profile_type == "Interviewee":
            print(f"[INTERVIEWEE] Fetching mapping for session {self.session_id}")
            mapping = await database_sync_to_async(cache.get)(mapping_cache_key(self.session_id), {})

            print(f"[MAPPING] {mapping}")

            interviewer_username = None
            for interviewer, q in mapping.items():
                if self.user.username in q:
                    interviewer_username = interviewer
                    break

            print(f"[INTERVIEWER FOUND FOR INTERVIEWEE] {interviewer_username}")

            if not interviewer_username:
                print("[CONNECT ERROR] Interviewee not assigned in mapping")
                await self.close(code=4004)
                return

            self.room_group_name = f"room_{interviewer_username}_{self.session_id}"
            print(f"[INTERVIEWEE JOINED ROOM] {self.room_group_name}")
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)

        else:
            print(f"[UNSUPPORTED PROFILE TYPE] {self.profile_type}")
            await self.close(code=4005)
            return
        await self._mark_user_online()
        print("========== CONNECT FINISHED ==========\n\n")

    async def disconnect(self, close_code):
        print("\n\n========== DISCONNECT STARTED ==========")
        print(f"[DISCONNECT] User = {getattr(self.user, 'username', '<unknown>')}")
        print(f"[DISCONNECT] Code = {close_code}")

        await self._mark_user_offline()

        if self.room_group_name:
            print(f"[DISCONNECT] Leaving Room = {self.room_group_name}")
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        if getattr(self, "profile_type", None) == "Interviewee":
            print("[DISCONNECT] Interviewee disconnect detected → handling queue logic")
            await self.***REMOVED***()

        print("========== DISCONNECT FINISHED ==========\n\n")

    @database_sync_to_async
    def _mark_user_online(self):
        key = online_users_cache_key(self.session_id)
        online = cache.get(key, {}) or {}
        online[self.user.username] = self.channel_name
        cache.set(key, online, timeout=60 * 60 * 10)


    @database_sync_to_async
    def _mark_user_offline(self):
        key = online_users_cache_key(self.session_id)
        online = cache.get(key, {}) or {}
        online.pop(self.user.username, None)
        cache.set(key, online, timeout=60 * 60 * 10)

    async def chat_message(self, event):
        print("[CHAT DELIVERY]", event)

        await self.send(text_data=json.dumps(event["message"]))

    async def receive(self, text_data=None, bytes_data=None):
        print("\n\n========== MESSAGE RECEIVED ==========")
        if not text_data:
            print("[RECEIVE ERROR] Empty message")
            return

        try:
            data = json.loads(text_data)
            print(f"[RECEIVED DATA] {data}")
        except Exception:
            print("[RECEIVE ERROR] Invalid JSON")
            return
        if self.profile_type == "Interviewee":
            await self._sync_room_with_mapping()
        action = data.get("action")
        print(f"[ACTION RECEIVED] {action}")

        # Control actions
        if action == "start_next":
            print("[ACTION] start_next triggered")
            if self.profile_type == "Interviewer":
                await self.start_next_interviewee()
            return

        if action == "accept_interview":
            print("[ACTION] accept_interview triggered")
            if self.profile_type == "Interviewee":
                await self.handle_accept()
            return

        if action == "reject_interview":
            print("[ACTION] reject_interview triggered")
            if self.profile_type == "Interviewee":
                await self.handle_reject()
            return

        if action == "complete_interview":
            print("[ACTION] complete_interview triggered")
            await self.handle_complete()
            return

        # if action == "leave":
        #     print("[ACTION] leave triggered")
        #     await self.handle_complete()
        #     return

        if action == "leave":
            print("[ACTION] leave triggered")

            if self.profile_type == "Interviewee":
                print("[LEAVE] Interviewee leaving → triggering disconnect handler")
                await self.***REMOVED***()

            elif self.profile_type == "Interviewer":
                print("[LEAVE] Interviewer ending interview → handle complete")
                await self.handle_complete()

            return
        
        if action == "get_all_queues":
            print("[ACTION] get_all_queues triggered")
            await self.handle_get_all_queues()
            return
        
        if action == "get_result":
            print("[ACTION] get_result triggered")
            await self.handle_get_result()
            return
        
        if action == "chat_message":
            print("[CHAT] Message Received")
            await self._handle_chat_message(data)
            return


        print("[ACTION] WebRTC signaling message forwarding")
        message = data.copy()
        message["sender"] = self.user.username

        print(f"[FORWARDING MESSAGE TO ROOM] {self.room_group_name} → {message}")
        await self.channel_layer.group_send(
            self.room_group_name,
            {"type": "webrtc_message", "message": message}
        )

        print("========== MESSAGE HANDLED ==========\n\n")

    async def webrtc_message(self, event):
        message = event.get("message", {})
        target = message.get("target")

        print("\n\n========== WEBRTC MESSAGE ==========")
        print(f"[WEBRTC MESSAGE RECEIVED] {message}")
        print(f"[TARGET] {target} | [CURRENT USER] {self.user.username}")

        if target and target != self.user.username:
            print("[WEBRTC] Target mismatch → SKIPPING message")
            return

        print("[WEBRTC] Sending message to client...")
        await self.send(text_data=json.dumps(message))
        print("========== WEBRTC SENT ==========\n\n")

    # -------------- QUEUE FUNCTIONS --------------

    async def start_next_interviewee(self):
        print("\n\n========== START NEXT CANDIDATE ==========")
        print(f"[START_NEXT] Interviewer = {self.user.username}")

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {}) or {}

        print(f"[START_NEXT] Mapping Loaded = {mapping}")

        queue = mapping.get(self.user.username, [])

        print(f"[START_NEXT] Queue for interviewer = {queue}")

        if not queue:
            print("[START_NEXT] NO MORE CANDIDATES")
            await self.send(text_data=json.dumps({"action": "no_more_candidates"}))
            return

        next_user = queue[0]
        print(f"[START_NEXT] Next Candidate = {next_user}")

        room = f"room_{self.user.username}_{self.session_id}"
        print(f"[START_NEXT] Sending start_interview to room = {room}")

        await self.channel_layer.group_send(
            room,
            {
                "type": "webrtc_message",
                "message": {
                    "action": "start_interview",
                    "target": next_user,
                    "interviewer": self.user.username,
                    "session_id": self.session_id,
                }
            }
        )

        print("========== START NEXT FINISHED ==========\n\n")

    async def handle_accept(self):
        print("\n\n========== ACCEPT HANDLER ==========")
        interviewee = self.user.username

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[ACCEPT] Mapping Loaded = {mapping}")

        interviewer = None
        for k, q in mapping.items():
            if q and q[0] == interviewee:
                interviewer = k
                break

        print(f"[ACCEPT] Interviewer Found = {interviewer}")

        if not interviewer:
            print("[ACCEPT ERROR] Interviewee not at queue head")
            await self.send(text_data=json.dumps({"action": "not_head"}))
            return

        room = f"room_{interviewer}_{self.session_id}"
        print(f"[ACCEPT] Sending acceptance to room = {room}")

        await self.channel_layer.group_send(
            room,
            {
                "type": "webrtc_message",
                "message": {
                    "action": "interview_accepted",
                    "interviewer": interviewer,
                    "interviewee": interviewee,
                }
            }
        )

        print("========== ACCEPT DONE ==========\n\n")

    async def handle_reject(self):
        print("\n\n========== REJECT HANDLER ==========")
        interviewee = self.user.username

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[REJECT] Mapping Loaded = {mapping}")

        interviewer = None
        for k, q in mapping.items():
            if interviewee in q:
                interviewer = k
                break

        print(f"[REJECT] Interviewer Found = {interviewer}")

        queue = mapping.get(interviewer, [])
        print(f"[REJECT] OLD QUEUE = {queue}")

        if interviewee in queue:
            queue.remove(interviewee)
        queue.append(interviewee)

        print(f"[REJECT] NEW QUEUE = {queue}")

        mapping[interviewer] = queue
        await database_sync_to_async(cache.set)(cache_key, mapping)

        room = f"room_{interviewer}_{self.session_id}"
        print(f"[REJECT] Notifying room = {room}")

        await self.channel_layer.group_send(
            room,
            {
                "type": "webrtc_message",
                "message": {
                    "action": "rejected_and_moved",
                    "interviewer": interviewer,
                    "interviewee": interviewee,
                    "new_queue": queue,
                }
            }
        )

        print("[REJECT] Triggering next candidate")
        await self.***REMOVED***(interviewer)

        print("========== REJECT DONE ==========\n\n")

    async def handle_complete(self):
        print("\n\n========== COMPLETE HANDLER ==========")

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[COMPLETE] Mapping Loaded = {mapping}")

        if self.profile_type == "Interviewer":
            interviewer = self.user.username
        else:
            interviewer = None
            for k, q in mapping.items():
                if q and q[0] == self.user.username:
                    interviewer = k
                    break

        print(f"[COMPLETE] Interviewer Identified = {interviewer}")

        queue = mapping.get(interviewer, [])
        print(f"[COMPLETE] OLD QUEUE = {queue}")

        if queue:
            finished = queue.pop(0)
        else:
            finished = None

        print(f"[COMPLETE] FINISHED = {finished}")
        print(f"[COMPLETE] NEW QUEUE = {queue}")

        mapping[interviewer] = queue
        await database_sync_to_async(cache.set)(cache_key, mapping)

        room = f"room_{interviewer}_{self.session_id}"
        print(f"[COMPLETE] Notifying room = {room}")

        await self.channel_layer.group_send(
            room,
            {
                "type": "webrtc_message",
                "message": {
                    "action": "interview_completed",
                    "interviewer": interviewer,
                    "finished": finished,
                    "new_queue": queue,
                }
            }
        )

        print("[COMPLETE] Triggering next candidate")
        await self.***REMOVED***(interviewer)

        print("========== COMPLETE DONE ==========\n\n")

    async def ***REMOVED***(self, interviewer_username: str):
        print("\n\n========== INTERNAL TRIGGER START ==========")
        print(f"[TRIGGER] Interviewer = {interviewer_username}")

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[TRIGGER] Mapping Loaded = {mapping}")

        queue = mapping.get(interviewer_username, [])
        print(f"[TRIGGER] Queue = {queue}")

        if not queue:
            print(f"[TRIGGER] Queue empty → sending no_more_candidates")
            await self.channel_layer.group_send(
                f"room_{interviewer_username}_{self.session_id}",
                {
                    "type": "webrtc_message",
                    "message": {
                        "action": "no_more_candidates",
                        "interviewer": interviewer_username
                    }
                }
            )
            return

        next_user = queue[0]
        print(f"[TRIGGER] Next Candidate = {next_user}")

        await self.channel_layer.group_send(
            f"room_{interviewer_username}_{self.session_id}",
            {
                "type": "webrtc_message",
                "message": {
                    "action": "start_interview",
                    "target": next_user,
                    "interviewer": interviewer_username,
                    "session_id": self.session_id,
                }
            }
        )

        print("========== INTERNAL TRIGGER FINISHED ==========\n\n")

    async def ***REMOVED***(self):
        print("\n\n========== DISCONNECT QUEUE CHECK ==========")
        disconnected = self.user.username
        print(f"[DISCONNECT QUEUE] User = {disconnected}")

        # ✅ Fetch user_profile_id
        user_profile_id = await self._get_user_profile_id()

        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[DISCONNECT QUEUE] Mapping = {mapping}")

        for interviewer, queue in mapping.items():
            print(f"[DISCONNECT QUEUE] Checking {interviewer} queue {queue}")

            # ✅ SEND disconnect even if user is NOT at head
            if disconnected in queue:

                room = f"room_{interviewer}_{self.session_id}"
                print(f"[DISCONNECT NOTICE] Notifying interviewer room {room}")

                # ✅ SEND DISCONNECT MESSAGE FOR ALL CASES
                await self.channel_layer.group_send(
                    room,
                    {
                        "type": "webrtc_message",
                        "message": {
                        "action": "interviewee_disconnected",
                        "interviewer": interviewer,
                        "interviewee": disconnected,
                        "user_profile_id": user_profile_id,
                        "session_id": self.session_id,
                        "reason": "interviewee_left",
                        "target": interviewer   # ✅ CRITICAL FIX
                    }
                    }
                )

                # ---- QUEUE CLEANUP -----
                if queue and queue[0] == disconnected:
                    print("[DISCONNECT QUEUE] HEAD left → triggering next")

                    queue.pop(0)
                    mapping[interviewer] = queue
                    await database_sync_to_async(cache.set)(cache_key, mapping)

                    # ✅ move queue ahead
                    await self.***REMOVED***(interviewer)

                else:
                    print("[DISCONNECT QUEUE] Removing from middle of queue")

                    queue = [u for u in queue if u != disconnected]
                    mapping[interviewer] = queue
                    await database_sync_to_async(cache.set)(cache_key, mapping)

        print("========== DISCONNECT QUEUE DONE ==========\n\n")



    async def get_active_interviewers(self) -> List[str]:
        print("\n\n========== FETCH ACTIVE INTERVIEWERS ==========")
        
        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})
        
        print(f"[ACTIVE] Mapping = {mapping}")
        
        # Return interviewers who have non-empty queues (active queues)
        active = [interviewer for interviewer, queue in mapping.items() if queue]
        
        print(f"[ACTIVE INTERVIEWERS] {active}")
        print("========== ACTIVE FETCH DONE ==========\n\n")
        
        return active


    async def handle_get_all_queues(self):
        print("\n\n========== GET ALL QUEUES ==========")

        # Load mapping
        cache_key = mapping_cache_key(self.session_id)
        mapping = await database_sync_to_async(cache.get)(cache_key, {})

        print(f"[GET_ALL_QUEUES] Mapping Loaded = {mapping}")

        # Determine active interviewers
        active_interviewers = await self.get_active_interviewers()

        print(f"[GET_ALL_QUEUES] Active Interviewers = {active_interviewers}")

        all_queues = {}

        for interviewer in active_interviewers:
            queue = mapping.get(interviewer, [])
            print(f"[QUEUE] {interviewer} = {queue}")
            all_queues[interviewer] = queue

        print(f"[GET_ALL_QUEUES] Final queues = {all_queues}")

        # Send ONLY to requesting client
        await self.send(text_data=json.dumps({
            "action": "all_queues",
            "queues": all_queues
        }))

        print("========== GET ALL QUEUES DONE ==========\n\n")

    @database_sync_to_async
    def _fetch_interview_result(self):
        try:
            from event.models import IntervieweeJoin, Event

            print(f"[GET RESULT] Session ID = {self.session_id}")

            # Fetch event
            event = Event.objects.filter(id=self.session_id).first()
            if not event:
                return {"status": "no_result"}   # event missing

            print(f"[GET RESULT] Event = {event}")
            print(f"[GET RESULT] User = {self.user.user_profile}")

            # Latest result for this candidate in this event
            join = (
                IntervieweeJoin.objects
                .filter(event=event, user=self.user.user_profile)
                .order_by("-id")
                .first()
            )

            if not join:
                return {"status": "no_result"}   # no result entry yet

            # Evaluate result
            if join.result == "pass":
                return {"status": "pass"}

            if join.result == "fail":
                return {"status": "fail"}

            # result field is NULL/None → pending
            return {"status": "pending"}

        except Exception as e:
            print("[GET RESULT ERROR]", e)
            return {"status": "error"}


    
    async def handle_get_result(self):
        print("\n\n========== GET RESULT HANDLER ==========")

        result = await self._fetch_interview_result()
        print(f"[RESULT] {result}")

        await self.send(text_data=json.dumps({
            "action": "get_result",
            "result": result["status"]
        }))

        print("========== GET RESULT DONE ==========\n\n")

    async def _get_user_profile_id(self):
        from user_data.models import UserProfile
        profile = await database_sync_to_async(UserProfile.objects.get)(user=self.user)
        print("\n\n========== GET USER PROFILE ID ==========")
        return profile.id
    
    async def _sync_room_with_mapping(self):
        """
        Ensure interviewee is always inside the correct interviewer room
        based on latest mapping in cache.
        """

        mapping = await database_sync_to_async(cache.get)(
            mapping_cache_key(self.session_id), {}
        )
        if not isinstance(mapping, dict):
            return  

        correct_interviewer = None
        for interviewer, users in mapping.items():
            if self.user.username in users:
                correct_interviewer = interviewer
                break

        # user removed from mapping
        if not correct_interviewer:
            return

        correct_room = f"room_{correct_interviewer}_{self.session_id}"

        # Already correct
        if self.room_group_name == correct_room:
            return

        print(f"[ROOM FIX] {self.user.username} moved → {self.room_group_name} → {correct_room}")

        # Leave wrong room
        if self.room_group_name:
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # Join right room
        self.room_group_name = correct_room
        await self.channel_layer.group_add(correct_room, self.channel_name)

        # Notify frontend (optional)
        await self.send(text_data=json.dumps({
            "action": "room_switched",
            "new_interviewer": correct_interviewer,
            "session_id": self.session_id
        }))

    async def _handle_chat_message(self, data):
        message = data.get("message", "").strip()

        if not message:
            print("[CHAT ERROR] Empty message")
            return

        print(f"[CHAT] {self.user.username}: {message}")

        payload = {
            "type": "chat_message",
            "message": {
                "action": "chat_message",
                "sender": self.user.username,
                "role": self.profile_type,
                "message": message,
                "session_id": self.session_id
            }
        }

        # Send chat message to entire interview room (interviewer + interviewee)
        await self.channel_layer.group_send(
            self.room_group_name,
            payload
        )


