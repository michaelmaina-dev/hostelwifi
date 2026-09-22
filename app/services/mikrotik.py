import routeros_api
from librouteros.exceptions import TrapError 

import routeros_api

from app.config import (
    MIKROTIK_HOST,
    MIKROTIK_USER,
    MIKROTIK_PASSWORD,
    MIKROTIK_PORT
)


class MikroTikService:
    def __init__(self):
        self.connection = routeros_api.RouterOsApiPool(
            host=MIKROTIK_HOST,
            username=MIKROTIK_USER,
            password=MIKROTIK_PASSWORD,
            port=MIKROTIK_PORT,
            plaintext_login=True
        )

        self.api = self.connection.get_api()

    def close(self):
        self.connection.disconnect()

    def get_interfaces(self):
        interface = self.api.get_resource("/interface")
        return interface.get()

    def get_ip_addresses(self):
        addresses = self.api.get_resource("/ip/address")
        return addresses.get()

    def get_system_resource(self):
        system = self.api.get_resource("/system/resource")
        return system.get()
    
    def get_dns(self):
        dns_reports=self.api.get_resource("/ip/dns")
        return dns_reports.get()
    
    def remove_user(self):
        try:
    
            hotspot = self.api.get_resource("/ip/hotspot/user")
            name = input("Enter hotspot user name you want to remove: ")
            user_list = hotspot.get(name=name)
            if user_list:
                mikrotik_id = user_list[0]['id']
                hotspot.remove(id=mikrotik_id)
                print(f"user {name} with id {mikrotik_id} has been removed")
            else:
                print(f"User name '{name}' not found in router database")
                
            return hotspot.get()
        
        except TrapError as e:
         print(f"Router API error occurred: {e}")
    
    def remove_hotspot_user(self, username):
        hotspot = self.api.get_resource("/ip/hotspot/user")
        existing = hotspot.get(name=username)

        if existing:
            hotspot.remove(id=existing[0]["id"])
    
    def add_user(self):
        user =self.api.get_resource("/ip/hotspot/user")
        name = input("Enter user name: ")
        password = input("Enter password: ")
        user.add(name=name, password=password)
        print(f"User {name} and password {password} added succefully")
        user.get()
    
    def all_users(self):
        users = self.api.get_resource("/ip/hotspot/user")
        return users.get()
    
    def create_simple_queue(self, name, target, max_limit):
        queue = self.api.get_resource("/queue/simple")

        queue.add(
            name=name,
            target=target,
            max_limit=max_limit
        )
    def create_hotspot_user(self, username, password, profile="default"):
        hotspot = self.api.get_resource("/ip/hotspot/user")

        existing = hotspot.get(name=username)

        if existing:
            mikrotik_id = existing[0]["id"]
            hotspot.set(id=mikrotik_id, password=password, profile=profile, disabled="no")
        else:
            hotspot.add(name=username, password=password, profile=profile)

    def get_hotspot_users(self):
        hotspot = self.api.get_resource("/ip/hotspot/user")
        return hotspot.get()
    
    def disable_hotspot_user(self, username):
        hotspot = self.api.get_resource("/ip/hotspot/user")
        active = self.api.get_resource("/ip/hotspot/active")

        user = hotspot.get(name=username)

        if user:
            # Disable the HotSpot account so it cannot log in again
            hotspot.set(
                id=user[0]["id"],
                disabled="yes"
            )

            # Remove any existing active session
            sessions = active.get(user=username)

        for session in sessions:
            active.remove(id=session["id"])
    
    def ensure_profile(self, profile_name, rate_limit, shared_users=1):
        profiles = self.api.get_resource("/ip/hotspot/user/profile")
        existing = profiles.get(name=profile_name)
        if existing:
            return
        profiles.add(
            name=profile_name,
            **{"rate-limit": rate_limit, "shared-users": str(shared_users)}
        )

    def get_active_user_bytes(self, username):
        """Return cumulative bytes (bytes-in + bytes-out) across ALL of a
        user's current active hotspot sessions, or None if they're not
        currently connected. Summing across sessions matters for any
        profile with shared-users > 1 — a customer connected on two
        devices at once shows up as two separate active-session records,
        and only reading the first one would silently undercount them by
        up to half their real usage.

        Used by BillingService.check_daily_quotas to track fair-use
        consumption; the caller is responsible for turning this raw
        cumulative counter into a daily delta, since the counter resets
        whenever a session itself restarts."""
        active = self.api.get_resource("/ip/hotspot/active")
        sessions = active.get(user=username)
        if not sessions:
            return None
        total = 0
        for session in sessions:
            total += int(session.get("bytes-in", 0))
            total += int(session.get("bytes-out", 0))
        return total

    def get_user_bytes(self, username):
        """Return a hotspot user's persistent, lifetime cumulative bytes
        (bytes-in + bytes-out), read from the user record itself — not the
        active-sessions table. Unlike active-session counters, this survives
        disconnects/reconnects, so it's safe to diff across polling gaps
        without losing usage from sessions that ended between checks.
        Returns None only if the user doesn't exist on the router at all."""
        hotspot = self.api.get_resource("/ip/hotspot/user")
        user = hotspot.get(name=username)
        if not user:
            return None
        bytes_in = int(user[0].get("bytes-in", 0))
        bytes_out = int(user[0].get("bytes-out", 0))
        return bytes_in + bytes_out

    def get_total_user_bytes(self, username):
        """Complete usage-so-far for a customer: persistent (completed-session)
        bytes from their user record, plus their current in-progress session(s)
        if connected right now. Continuous across connect/disconnect — when a
        session ends, RouterOS folds its bytes into the persistent counter at
        the same moment the active-session component drops to zero, so the
        combined total never jumps or loses data. Sums multiple simultaneous
        sessions (shared_users > 1). Returns None only if the user doesn't
        exist on the router at all."""
        hotspot = self.api.get_resource("/ip/hotspot/user")
        user = hotspot.get(name=username)
        if not user:
            return None

        persistent_bytes = int(user[0].get("bytes-in", 0)) + int(user[0].get("bytes-out", 0))

        active = self.api.get_resource("/ip/hotspot/active")
        sessions = active.get(user=username)
        active_bytes = sum(
            int(s.get("bytes-in", 0)) + int(s.get("bytes-out", 0))
            for s in sessions
        ) if sessions else 0

        return persistent_bytes + active_bytes
    
    def set_user_profile(self, username, profile_name):
        """Switch an existing hotspot user onto a different profile
        (e.g. moving them onto a fair-use throttle profile, or back to
        their normal package profile) without touching their password
        or disabled state."""
        hotspot = self.api.get_resource("/ip/hotspot/user")
        user = hotspot.get(name=username)
        if user:
            hotspot.set(id=user[0]["id"], profile=profile_name)
