"""Curated travel phrase packs for quick translation mode."""

from __future__ import annotations

from typing import Dict, List

TRAVEL_CATEGORIES: Dict[str, str] = {
    "greetings": "Greetings",
    "transport": "Transport",
    "hotel": "Hotel",
    "food": "Food",
    "shopping": "Shopping",
    "emergency": "Emergency",
}

TRAVEL_PHRASES: Dict[str, List[str]] = {
    "greetings": [
        "Hello",
        "Good morning",
        "How are you?",
        "Thank you",
        "Please",
        "Goodbye",
    ],
    "transport": [
        "Where is the bus station?",
        "I need a taxi",
        "How much is the fare?",
        "Please stop here",
        "What time does it leave?",
        "Can you show me on the map?",
    ],
    "hotel": [
        "I have a reservation",
        "I need a room for one night",
        "What time is check-out?",
        "Is breakfast included?",
        "The room key is not working",
        "Can I get the Wi-Fi password?",
    ],
    "food": [
        "I would like to order food",
        "What do you recommend?",
        "I am vegetarian",
        "No spicy food, please",
        "Can I have water?",
        "Can I get the bill, please?",
    ],
    "shopping": [
        "How much does this cost?",
        "That is too expensive",
        "Do you have another size?",
        "Can I pay by card?",
        "I am just looking",
        "Can you lower the price?",
    ],
    "emergency": [
        "I need help",
        "Call the police",
        "I need a doctor",
        "Where is the nearest hospital?",
        "I lost my phone",
        "Please help me find this address",
    ],
}
