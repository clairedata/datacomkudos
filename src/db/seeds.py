"""
PROJECT: Datacom Kudos System
FILE: src/db/seeds.py
DESCRIPTION: Initial seed records for Datacom employees directory and demo kudos
"""

# Initial Datacom employee seed records
INITIAL_USERS = [
    {
        "id": "u-01",
        "name": "Sarah Connor",
        "email": "sarah.c@datacom.com",
        "role": "user",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=Sarah&backgroundColor=b6e3f4",
        "department": "Cloud Solutions",
        "is_active": 1,
    },
    {
        "id": "u-02",
        "name": "James Vance",
        "email": "james.v@datacom.com",
        "role": "user",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=James&backgroundColor=c0aede",
        "department": "DevOps & Reliability",
        "is_active": 1,
    },
    {
        "id": "u-03",
        "name": "Thomas Wright",
        "email": "thomas.w@datacom.com",
        "role": "admin",  # Administrator / Moderator role
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=Thomas&backgroundColor=ffd5dc",
        "department": "People & Culture (HR)",
        "is_active": 1,
    },
    {
        "id": "u-04",
        "name": "Alice Martin",
        "email": "alice.m@datacom.com",
        "role": "user",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=Alice&backgroundColor=d1d4f9",
        "department": "Software Engineering",
        "is_active": 1,
    },
    {
        "id": "u-05",
        "name": "David Chen",
        "email": "david.c@datacom.com",
        "role": "user",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=David&backgroundColor=ffdfbf",
        "department": "Cybersecurity & Compliance",
        "is_active": 1,
    },
    {
        "id": "u-06",
        "name": "Lucas Moreau (Inactive)",
        "email": "lucas.m@datacom.com",
        "role": "user",
        "avatar": "https://api.dicebear.com/7.x/avataaars/svg?seed=Lucas&backgroundColor=e0e0e0",
        "department": "Former Contractor",
        "is_active": 0,  # Inactive account used to test business rule BR-02
    },
]

# Initial sample kudos records for demonstration
INITIAL_KUDOS = [
    {
        "id": "k-001",
        "sender_id": "u-01",
        "recipient_id": "u-02",
        "category": "Teamwork",
        "message": "Huge thanks for stepping in and resolving the cloud network outage so swiftly this morning!",
        "is_visible": 1,
        "moderated_by": None,
        "moderated_at": None,
        "reason_for_moderation": None,
        "ai_flagged": 0,
        "ai_flag_reason": None,
    },
    {
        "id": "k-002",
        "sender_id": "u-04",
        "recipient_id": "u-01",
        "category": "Innovation",
        "message": "Outstanding architecture presentation for the customer portal revamp, crystal clear explanation!",
        "is_visible": 1,
        "moderated_by": None,
        "moderated_at": None,
        "reason_for_moderation": None,
        "ai_flagged": 0,
        "ai_flag_reason": None,
    },
    {
        "id": "k-003",
        "sender_id": "u-05",
        "recipient_id": "u-04",
        "category": "Above & Beyond",
        "message": "Insane effort delivering the weekend migration on schedule, thank you for your commitment!",
        "is_visible": 1,
        "moderated_by": None,
        "moderated_at": None,
        "reason_for_moderation": None,
        "ai_flagged": 1,  # Flagged for administrator review demonstration
        "ai_flag_reason": "AI Alert: Intensive tone or potential burnout expression detected",
    },
]
