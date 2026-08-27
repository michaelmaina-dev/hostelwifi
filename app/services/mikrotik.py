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

        user = hotspot.get(name=username)

        if user:
            hotspot.set(id=user[0]["id"], disabled="yes")
    
    def ensure_profile(self, profile_name, rate_limit, shared_users=1):
        profiles = self.api.get_resource("/ip/hotspot/user/profile")
        existing = profiles.get(name=profile_name)
        if existing:
            return
        profiles.add(
            name=profile_name,
            **{"rate-limit": rate_limit, "shared-users": str(shared_users)}
        )